"""Painel de avaliação de um critério (Módulo II): caracterização, evidências e apontamentos.

Layout em listas agrupadas (inset grouped) do iOS: cada bloco é um cartão branco
sobre o fundo cinza, com cabeçalho de seção acima e nota de rodapé abaixo.
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QFontMetrics
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout, QWidget

from ..core.model import Criterion, NormModel
from ..core.rules import Snapshot
from ..core.storage import Evidence
from . import theme as T
from .findings import FindingCard
from .widgets import (Card, SectionHeader, SegmentedRating, Switch, button, clear_layout, icon_button, label,
                      section_footer, separator, set_variant)

# modos de exibição de um item
EDIT = "edit"                  # avaliação inicial em andamento
LOCKED = "locked"              # avaliação inicial concluída (somente leitura)
FINAL = "final"                # avaliação final: revisita de item com apontamento
FINAL_LOCKED = "final_locked"  # avaliação final concluída
FINAL_FIXED = "final_fixed"    # avaliação final, item sem apontamento (mantém a nota inicial)


class _ElidedLabel(QLabel):
    def __init__(self, text: str):
        super().__init__()
        self._full = text
        self.setFont(T.font(T.BODY))
        self.setToolTip(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setStyleSheet(f"color: {T.LABEL}; background: transparent;")

    def resizeEvent(self, e):
        self.setText(QFontMetrics(self.font()).elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width()))
        super().resizeEvent(e)


class EvidenceRow(QWidget):
    removeRequested = pyqtSignal(int)

    def __init__(self, ev: Evidence, readonly: bool):
        super().__init__()
        self.ev = ev
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 9, 10, 9)
        lay.setSpacing(12)
        if not readonly:
            rm = icon_button("minus-circle", "Remover evidência", T.RED, 18)
            rm.setStyleSheet("QToolButton { border: none; padding: 0px; background: transparent; }")
            rm.clicked.connect(lambda: self.removeRequested.emit(ev.id))
            lay.addWidget(rm)
        ic = QLabel()
        ic.setPixmap(T.icon("doc-text" if ev.kind == "arquivo" else "note", T.SECONDARY, 17).pixmap(17, 17))
        ic.setStyleSheet("background: transparent;")
        lay.addWidget(ic)
        lay.addWidget(_ElidedLabel(ev.content), 1)
        if ev.kind == "arquivo":
            b = button("Abrir", "ghost")
            b.setToolTip(ev.content)
            b.clicked.connect(lambda: QDesktopServices.openUrl(
                QUrl(ev.content) if "://" in ev.content else QUrl.fromLocalFile(ev.content)))
            lay.addWidget(b)


class ItemEditor(QWidget):
    """Conteúdo rolável do critério atual. Emite mudanças; a persistência fica no workspace."""
    ratingChanged = pyqtSignal(str, object)
    finalRatingChanged = pyqtSignal(str, object)
    evidenceAdded = pyqtSignal(str, str, str)       # item, kind, content
    evidenceRemoved = pyqtSignal(str, int)
    findingEdited = pyqtSignal(int, str, object)    # apontamento, campo, valor
    findingAddRequested = pyqtSignal(str)
    findingLinkRequested = pyqtSignal(int)
    findingUnlinkRequested = pyqtSignal(int)
    findingDeleteRequested = pyqtSignal(int)

    def __init__(self, model: NormModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.cid: str | None = None
        self.readonly = False
        self.mode = EDIT
        self._loading = False
        self._cards: dict[int, FindingCard] = {}
        self.setAcceptDrops(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 26, 40, 40)
        outer.setSpacing(0)

        # ------------------------------------------------ cabeçalho
        crumb_row = QHBoxLayout()
        crumb_row.setContentsMargins(4, 0, 4, 0)
        self.crumb = label("", T.FOOTNOTE, color=T.SECONDARY)
        crumb_row.addWidget(self.crumb)
        crumb_row.addStretch(1)
        self.position = label("", T.FOOTNOTE, color=T.SECONDARY)
        crumb_row.addWidget(self.position)
        outer.addLayout(crumb_row)
        outer.addSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 4, 0)
        head.setSpacing(12)
        self.code = label("", T.LARGE_TITLE + 4, QFont.Weight.Bold, display=True)
        head.addWidget(self.code, 0, Qt.AlignmentFlag.AlignBottom)
        self.title = label("", T.TITLE_2, QFont.Weight.DemiBold, wrap=True, display=True)
        head.addWidget(self.title, 1, Qt.AlignmentFlag.AlignBottom)
        outer.addLayout(head)
        outer.addSpacing(18)

        # ------------------------------------------------ resultado esperado
        outer.addWidget(SectionHeader("Resultado esperado"))
        outer.addSpacing(6)
        self.norm_card = Card()
        self.text = label("", T.BODY + 0.5, color=T.LABEL, wrap=True, selectable=True)
        self.text.setContentsMargins(16, 13, 16, 13)
        self.norm_card.lay.addWidget(self.text)
        self.notes_box = QVBoxLayout()
        self.notes_box.setSpacing(0)
        self.norm_card.lay.addLayout(self.notes_box)
        # linha "Onde procurar evidências" com switch
        self.hint_sep = separator(16)
        self.norm_card.lay.addWidget(self.hint_sep)
        hint_row = QWidget()
        hr = QHBoxLayout(hint_row)
        hr.setContentsMargins(16, 9, 14, 9)
        hr.setSpacing(10)
        bulb = QLabel()
        bulb.setPixmap(T.icon("bulb", T.ORANGE, 17).pixmap(17, 17))
        bulb.setStyleSheet("background: transparent;")
        hr.addWidget(bulb)
        hr.addWidget(label("Onde procurar evidências", T.BODY), 1)
        self.hint_btn = Switch()
        self.hint_btn.setToolTip("Mostrar sugestões de evidência para cada critério")
        self.hint_btn.setChecked(QSettings().value("show_hints", False, type=bool))
        self.hint_btn.toggled.connect(self._toggle_hint)
        hr.addWidget(self.hint_btn)
        self.hint_row = hint_row
        self.norm_card.lay.addWidget(hint_row)
        self.hint = label("", T.CALLOUT, color=T.LABEL_2, wrap=True)
        self.hint.setContentsMargins(43, 0, 16, 13)
        self.norm_card.lay.addWidget(self.hint)
        outer.addWidget(self.norm_card)

        # ------------------------------------------------ caracterização
        outer.addSpacing(26)
        self.rating_title = SectionHeader("Caracterização", "teclas 1 a 4")
        outer.addWidget(self.rating_title)
        outer.addSpacing(6)
        rating_card = Card(padding=(8, 8, 8, 8))
        self.rating = SegmentedRating(model.scale)
        self.rating.ratingChanged.connect(lambda code: self.cid and self.ratingChanged.emit(self.cid, code))
        rating_card.lay.addWidget(self.rating)
        outer.addWidget(rating_card)

        # ------------------------------------------------ evidências
        outer.addSpacing(26)
        self.ev_title = SectionHeader("Evidências", "obrigatória ao menos uma")
        outer.addWidget(self.ev_title)
        outer.addSpacing(6)
        self.ev_card = Card()
        self.ev_list = QVBoxLayout()
        self.ev_list.setSpacing(0)
        self.ev_card.lay.addLayout(self.ev_list)
        self.input_row = QWidget()
        ir = QHBoxLayout(self.input_row)
        ir.setContentsMargins(16, 6, 8, 6)
        ir.setSpacing(12)
        plus = QLabel()
        plus.setPixmap(T.icon("plus-circle", T.GREEN, 18).pixmap(18, 18))
        plus.setStyleSheet("background: transparent;")
        ir.addWidget(plus)
        self.ev_input = QLineEdit()
        self.ev_input.setProperty("role", "cell")
        self.ev_input.setFont(T.font(T.BODY))
        self.ev_input.setPlaceholderText("Adicionar evidência: descreva, cole um caminho ou link")
        self.ev_input.returnPressed.connect(self._add_text)
        self.ev_input.textChanged.connect(self._morph_attach)
        self.ev_input.setMinimumHeight(30)
        ir.addWidget(self.ev_input, 1)
        self.attach = button("Anexar arquivo", "ghost", "paperclip")
        self.attach.clicked.connect(lambda: self._add_text() if self.ev_input.text().strip() else self._attach())
        ir.addWidget(self.attach)
        self.ev_card.lay.addWidget(self.input_row)
        outer.addWidget(self.ev_card)
        outer.addSpacing(6)
        self.ev_footer = section_footer("Você também pode arrastar arquivos para esta tela.")
        outer.addWidget(self.ev_footer)

        # ------------------------------------------------ apontamento (Relatório de Ajustes)
        self.find_section = QWidget()
        fs = QVBoxLayout(self.find_section)
        fs.setContentsMargins(0, 22, 0, 0)
        fs.setSpacing(0)
        self.find_title = SectionHeader("Apontamento")
        fs.addWidget(self.find_title)
        fs.addSpacing(6)
        self.find_box = QVBoxLayout()
        self.find_box.setSpacing(12)
        fs.addLayout(self.find_box)
        add_row = QHBoxLayout()
        add_row.setContentsMargins(8, 4, 0, 0)
        self.add_find_btn = button("Adicionar outro apontamento", "ghost", "plus")
        self.add_find_btn.clicked.connect(lambda: self.cid and self.findingAddRequested.emit(self.cid))
        add_row.addWidget(self.add_find_btn)
        add_row.addStretch(1)
        fs.addLayout(add_row)
        self.find_footer = section_footer("")
        fs.addSpacing(4)
        fs.addWidget(self.find_footer)
        outer.addWidget(self.find_section)

        # ------------------------------------------------ avaliação final: nova caracterização
        self.final_section = QWidget()
        fl = QVBoxLayout(self.final_section)
        fl.setContentsMargins(0, 26, 0, 0)
        fl.setSpacing(0)
        self.final_title = SectionHeader("Nova caracterização", "avaliação final · teclas 1 a 5")
        fl.addWidget(self.final_title)
        fl.addSpacing(6)
        self.final_card = Card(padding=(8, 8, 8, 8))
        self.final_rating = SegmentedRating(model.final_scale)
        self.final_rating.setAccessibleName("Nova caracterização")
        self.final_rating.ratingChanged.connect(lambda code: self.cid and self.finalRatingChanged.emit(self.cid, code))
        self.final_card.lay.addWidget(self.final_rating)
        fl.addWidget(self.final_card)
        # aviso da regra do requerido "Leve" (Guia de Avaliação 2024, Parte I, p. 58): aparece quando a
        # empresa não corrigiu um requerido leve. Com T, deixa explícito que a nota subiu pela regra e que o
        # problema continua como ponto fraco; sem T, só informa que o T é permitido.
        self.leve_note = QWidget()
        ln = QVBoxLayout(self.leve_note)
        ln.setContentsMargins(0, 10, 0, 0)
        self.leve_card = Card(padding=(14, 11, 14, 11))
        lrow = QHBoxLayout()
        lrow.setSpacing(10)
        self.leve_icon = QLabel()
        self.leve_icon.setStyleSheet("background: transparent;")
        lrow.addWidget(self.leve_icon, 0, Qt.AlignmentFlag.AlignTop)
        ltxt = QVBoxLayout()
        ltxt.setSpacing(2)
        self.leve_title = label("", T.CALLOUT, QFont.Weight.DemiBold, T.LABEL, wrap=True)
        self.leve_body = label("", T.FOOTNOTE, color=T.LABEL_2, wrap=True)
        ltxt.addWidget(self.leve_title)
        ltxt.addWidget(self.leve_body)
        lrow.addLayout(ltxt, 1)
        self.leve_card.lay.addLayout(lrow)
        ln.addWidget(self.leve_card)
        fl.addWidget(self.leve_note)
        fl.addSpacing(6)
        self.final_footer = section_footer("Caracterização após os ajustes. NA: o resultado não pôde ser evidenciado "
                                           "pelo estágio do projeto.")
        fl.addWidget(self.final_footer)
        outer.addWidget(self.final_section)

        # ------------------------------------------------ aviso de item sem ajustes (avaliação final)
        self.fixed_note = QWidget()
        fn = QVBoxLayout(self.fixed_note)
        fn.setContentsMargins(0, 22, 0, 0)
        note_card = Card(padding=(16, 12, 16, 12))
        self.fixed_lbl = label("", T.CALLOUT, color=T.LABEL_2, wrap=True)
        note_card.lay.addWidget(self.fixed_lbl)
        fn.addWidget(note_card)
        outer.addWidget(self.fixed_note)
        outer.addStretch(1)

    # ------------------------------------------------------------ carga
    def show_item(self, c: Criterion, snap: Snapshot, mode: str = EDIT, position: str = ""):
        self.flush()
        self._loading = True
        self.cid = c.id
        self.mode = mode
        self.readonly = mode != EDIT
        self.position.setText(position)
        proc = self.model.process(c.process)
        self.crumb.setText(f"{proc.name}  ›  {c.group}")
        self.code.setText(c.code)
        self.title.setText(c.title)
        self.text.setText(c.text)

        clear_layout(self.notes_box)
        for n in c.notes:
            self.notes_box.addWidget(separator(16))
            self.notes_box.addWidget(self._note(n.kind, n.text))

        self.hint.setText(c.hint)
        has_hint = bool(c.hint)
        self.hint_sep.setVisible(has_hint)
        self.hint_row.setVisible(has_hint)
        self.hint.setVisible(has_hint and self.hint_btn.isChecked())

        ans = snap.answer(c.id)
        final_phase = mode in (FINAL, FINAL_LOCKED, FINAL_FIXED)
        self.rating_title.title.setText("Caracterização na avaliação inicial" if final_phase else "Caracterização")
        self.rating_title.set_aside("" if self.readonly else "teclas 1 a 4")
        self.rating.set_value(ans.rating)
        self.rating.setEnabled(not self.readonly)
        self._render_evidences(ans.evidences)
        self.input_row.setVisible(not self.readonly)
        self.ev_input.clear()

        self.final_section.setVisible(mode in (FINAL, FINAL_LOCKED))
        self.final_rating.set_value(ans.final_rating)
        self.final_rating.setEnabled(mode == FINAL)
        self.final_title.set_aside("avaliação final · teclas 1 a 5" if mode == FINAL else "avaliação final")
        self.fixed_note.setVisible(mode == FINAL_FIXED)
        r = snap.initial(c.id)
        self.fixed_lbl.setText(f"Sem apontamento na avaliação inicial: o resultado mantém a caracterização "
                               f"{r.code if r else '—'} na avaliação final.")
        self.render_findings(snap)
        self._loading = False

    def render_findings(self, snap: Snapshot):
        """Reconstrói os cartões de apontamento do item aberto."""
        for card in self._cards.values():
            card.flush()
        clear_layout(self.find_box)
        self._cards = {}
        cid = self.cid
        kind = snap.item_kind(cid) if cid else None
        visible = bool(kind) and self.mode != FINAL_FIXED
        self.find_section.setVisible(visible)
        if not visible:
            return
        lb = self.model.labels
        if kind == "requerido":
            self.find_title.title.setText(f"{lb.description_req} e {lb.suggestion.lower()}")
        else:
            self.find_title.title.setText(lb.description_mel)
        card_mode = {EDIT: "edit", LOCKED: "locked", FINAL: "final", FINAL_LOCKED: "final_locked"}[self.mode]
        fs = [f for f in snap.item_findings(cid) if snap.finding_kind(f)]
        for i, f in enumerate(fs):
            others = [self.model.criterion(x).code for x in snap.active_items(f) if x != cid]
            card = FindingCard(self.model, f, snap.finding_kind(f), others, card_mode, i + 1 if len(fs) > 1 else 0)
            card.edited.connect(self.findingEdited.emit)
            card.linkRequested.connect(self.findingLinkRequested.emit)
            card.unlinkRequested.connect(self.findingUnlinkRequested.emit)
            card.deleteRequested.connect(self.findingDeleteRequested.emit)
            self.find_box.addWidget(card)
            self._cards[f.id] = card
        if not fs:
            empty = Card(padding=(16, 12, 16, 12))
            empty.lay.addWidget(label("Nenhum apontamento registrado.", T.BODY, color=T.SECONDARY))
            self.find_box.addWidget(empty)
        self.add_find_btn.setVisible(self.mode == EDIT)
        self.add_find_btn.setText("Adicionar outro apontamento" if fs else "Adicionar apontamento")
        self.refresh_requirements(snap)

    def update_findings(self, snap: Snapshot):
        """Atualiza cartões existentes (valores não textuais e pendências) sem reconstruí-los."""
        by_id = {f.id: f for f in snap.findings}
        for fid, card in self._cards.items():
            if fid in by_id:
                card.update_from(by_id[fid])

    def _note(self, kind: str, text: str) -> QWidget:
        req = kind == "requerido"
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 10, 16, 11)
        lay.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(6)
        ic = QLabel()
        ic.setPixmap(T.icon("alert-circle" if req else "doc-text", T.BLUE if req else T.SECONDARY, 14).pixmap(14, 14))
        ic.setStyleSheet("background: transparent;")
        top.addWidget(ic)
        top.addWidget(label("Item requerido" if req else "Nota informativa", T.FOOTNOTE, QFont.Weight.DemiBold,
                            T.BLUE_TEXT if req else T.SECONDARY))
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(label(text, T.CALLOUT, color=T.LABEL_2 if req else T.SECONDARY, wrap=True))
        return w

    def _render_evidences(self, evs: list[Evidence]):
        clear_layout(self.ev_list)
        for i, ev in enumerate(evs):
            if i:
                self.ev_list.addWidget(separator(self._sep_inset()))
            r = EvidenceRow(ev, self.readonly)
            r.removeRequested.connect(lambda eid: self.cid and self.evidenceRemoved.emit(self.cid, eid))
            self.ev_list.addWidget(r)
        if evs and not self.readonly:
            self.ev_list.addWidget(separator(self._sep_inset()))
        if self.readonly and not evs:
            empty = label("Nenhuma evidência registrada.", T.BODY, color=T.SECONDARY)
            empty.setContentsMargins(16, 12, 16, 12)
            self.ev_list.addWidget(empty)
        self.ev_footer.setVisible(not self.readonly)

    def _sep_inset(self) -> int:
        return 16 + (30 if not self.readonly else 0) + 29

    def set_evidences(self, evs: list[Evidence]):
        self._render_evidences(evs)

    def refresh_requirements(self, snap: Snapshot):
        cid = self.cid
        if not cid:
            return
        ans = snap.answer(cid)
        kind = snap.item_kind(cid)
        missing_any = False
        for card in self._cards.values():
            keys = card.missing_keys(snap, cid)
            card.set_missing(keys)
            missing_any |= bool(keys)
        if self.mode == EDIT and kind and not self._cards:
            missing_any = True
        if self.mode == EDIT and kind:
            need = "obrigatórios para P e N" if kind == "requerido" else "obrigatória para L"
            self.find_title.set_aside(need, T.TONE_TEXT["warn"] if missing_any else T.SECONDARY)
            self.find_footer.setText("Este texto entra no Relatório de Ajustes para a Avaliação Final."
                                     if not missing_any else
                                     ("Registre o ponto fraco e o que a empresa deve corrigir." if kind == "requerido"
                                      else "Registre a oportunidade de melhoria que justifica o L."))
        elif self.mode == FINAL:
            self.find_title.set_aside("registre a correção da empresa",
                                      T.TONE_TEXT["warn"] if missing_any else T.SECONDARY)
            self.find_footer.setText("Correção realizada é obrigatória quando a empresa corrigiu.")
        else:
            self.find_title.set_aside("")
            self.find_footer.setText("")
        self.find_footer.setVisible(bool(self.find_footer.text()))
        no_ev = not ans.evidences and bool(ans.rating) and self.mode == EDIT
        self.ev_title.set_aside("obrigatória ao menos uma" if self.mode == EDIT else "",
                                T.TONE_TEXT["warn"] if no_ev else T.SECONDARY)
        self.ev_card.set_invalid(no_ev)
        no_final = self.mode == FINAL and not ans.final_rating
        self.final_card.set_invalid(no_final)
        self._refresh_leve(snap)

    def _refresh_leve(self, snap: Snapshot):
        """Mostra o aviso do requerido leve na nova caracterização (ver rules.Snapshot.kept_as_weak)."""
        cid = self.cid
        show = self.mode in (FINAL, FINAL_LOCKED) and snap.leve_allows_t(cid)
        self.leve_note.setVisible(show)
        if not show:
            return
        initial = snap.initial(cid).code
        if snap.kept_as_weak(cid):
            # caso que o avaliador precisa enxergar: a nota subiu de P/N para T sem correção da empresa
            self.leve_icon.setPixmap(T.icon("flag", T.ORANGE, 18, 2.0).pixmap(18, 18))
            self.leve_title.setText(f"{initial} → T por requerido leve")
            self.leve_title.setStyleSheet(f"color: {T.TONE_TEXT['warn']}; background: transparent;")
            self.leve_body.setText("A empresa não corrigiu, mas o problema foi classificado como Leve. Pelo Guia de "
                                   "Avaliação 2024 (Parte I, p. 58), o resultado pode ficar T. O problema continua "
                                   "registrado como ponto fraco no relatório final.")
            self.leve_card.setStyleSheet(f"#Card {{ background: {T.TONE_SOFT['warn']}; border-radius: {T.RADIUS_CARD}px; }}")
        else:
            self.leve_icon.setPixmap(T.icon("bulb", T.BLUE, 18, 2.0).pixmap(18, 18))
            self.leve_title.setText("Requerido leve sem correção")
            self.leve_title.setStyleSheet(f"color: {T.BLUE_TEXT}; background: transparent;")
            self.leve_body.setText(f"O guia permite caracterizar como T mesmo sem a correção. Se escolher T, a nota "
                                   f"sobe de {initial} para T e o problema continua como ponto fraco.")
            self.leve_card.setStyleSheet(f"#Card {{ background: {T.BLUE_TINT}; border-radius: {T.RADIUS_CARD}px; }}")

    def first_missing_card(self, snap: Snapshot) -> FindingCard | None:
        for card in self._cards.values():
            if card.missing_keys(snap, self.cid):
                return card
        return None

    def focus_finding(self, snap: Snapshot) -> bool:
        card = self.first_missing_card(snap) or next(iter(self._cards.values()), None)
        if card is None:
            return False
        return card.focus_first(card.missing_keys(snap, self.cid) or None)

    # ------------------------------------------------------------ ações
    def _toggle_hint(self, on: bool):
        self.hint.setVisible(on and bool(self.hint.text()))
        QSettings().setValue("show_hints", on)

    def _morph_attach(self, text: str):
        """Com texto digitado, o botão passa a adicionar a evidência; vazio, anexa arquivo."""
        typing = bool(text.strip())
        if typing == (self.attach.property("variant") == "primary"):
            return
        set_variant(self.attach, "primary" if typing else "ghost")
        self.attach.setText("Adicionar" if typing else "Anexar arquivo")
        self.attach.setIcon(T.icon("plus", "#FFFFFF", 16) if typing else T.icon("paperclip", T.BLUE, 16))
        self.attach.setToolTip("Adicionar a evidência digitada (Enter)" if typing else "Selecionar arquivos de evidência")

    def _add_text(self):
        txt = self.ev_input.text().strip()
        if not txt or not self.cid or self.readonly:
            return
        unquoted = txt.strip('"').strip("'")
        kind = "arquivo" if ("://" in unquoted or os.path.exists(unquoted)) else "texto"
        self.evidenceAdded.emit(self.cid, kind, unquoted if kind == "arquivo" else txt)
        self.ev_input.clear()

    def _attach(self):
        if not self.cid:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Anexar evidências", str(Path.home()))
        for p in paths:
            self.evidenceAdded.emit(self.cid, "arquivo", p)

    def flush(self):
        for card in self._cards.values():
            card.flush()

    def focus_evidence(self):
        if not self.readonly:
            self.ev_input.setFocus()

    # ------------------------------------------------------------ arrastar e soltar
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and not self.readonly:
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile() or url.toString()
            if path and self.cid:
                self.evidenceAdded.emit(self.cid, "arquivo", path)
        e.acceptProposedAction()

    def sizeHint(self):
        return QSize(780, 900)
