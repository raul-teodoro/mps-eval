"""Apontamentos do Relatório de Ajustes: cartão de edição e diálogo "Aplicar também a…".

Um apontamento é uma linha do Relatório de Ajustes para a Avaliação Final:
* REQUERIDO (P ou N): Problema + Sugestão de correção;
* MELHORIA (L): Oportunidade de melhoria.
Na avaliação final, o mesmo cartão recebe a situação da correção e a correção realizada.
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QMenu, QPlainTextEdit, QScrollArea,
                             QSizePolicy, QVBoxLayout, QWidget)

from ..core.model import NormModel
from ..core.rules import IMPACT_LEVE, Snapshot
from ..core.storage import Finding
from . import theme as T
from .widgets import (Card, Option, SectionHeader, Segmented, SelectRow, button, chip, grouped_rows, icon_button,
                      label, section_footer, separator)

KIND_STYLE = {"requerido": (T.TONE_TEXT["warn"], T.TONE_SOFT["warn"]),
              "melhoria": (T.BLUE_TEXT, T.BLUE_TINT)}


class AutoText(QPlainTextEdit):
    """Campo de texto que cresce com o conteúdo (entre um mínimo e um máximo)."""

    def __init__(self, placeholder: str, min_h: int = 66, max_h: int = 260):
        super().__init__()
        self.setProperty("role", "cell")
        self.setFont(T.font(T.BODY))
        self.setPlaceholderText(placeholder)
        self.setTabChangesFocus(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._min, self._max = min_h, max_h
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self.setFixedHeight(min_h)

    def _fit(self, *_):
        lines = max(1.0, self.document().size().height())
        h = int(lines * self.fontMetrics().lineSpacing() + 2 * self.document().documentMargin() + 10)
        self.setFixedHeight(max(self._min, min(self._max, h)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()


class FindingCard(Card):
    """Cartão de um apontamento ligado ao resultado aberto."""
    edited = pyqtSignal(int, str, object)       # finding id, campo, valor
    linkRequested = pyqtSignal(int)
    unlinkRequested = pyqtSignal(int)
    deleteRequested = pyqtSignal(int)

    def __init__(self, model: NormModel, f: Finding, kind: str, others: list[str], mode: str, index: int = 0):
        """mode: "edit" (avaliação inicial), "locked", "final" (revisita) ou "final_locked"."""
        super().__init__()
        self.model, self.f, self.kind, self.mode = model, f, kind, mode
        lb = model.labels
        edit = mode == "edit"
        final = mode in ("final", "final_locked")
        self._timers: dict[str, QTimer] = {}
        self._loading = True

        # ---------------- cabeçalho: tipo, compartilhamento e ações
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 10, 8, 8)
        hl.setSpacing(8)
        fg, bg = KIND_STYLE[kind]
        hl.addWidget(chip(lb.requerido if kind == "requerido" else lb.melhoria, fg, bg))
        if index:
            hl.addWidget(label(f"Apontamento {index}", T.FOOTNOTE, QFont.Weight.Medium, T.SECONDARY))
        self.shared = label("", T.FOOTNOTE, color=T.SECONDARY)
        if others:
            self.shared.setText("Compartilhado com " + ", ".join(others))
            self.shared.setToolTip("O mesmo texto vale para todos esses resultados. Editar aqui atualiza todos.")
        hl.addWidget(self.shared)
        hl.addStretch(1)
        if edit:
            self.link_btn = button("Aplicar também a…", "ghost", "link")
            self.link_btn.setToolTip("Usar este mesmo apontamento em outros resultados do processo")
            self.link_btn.clicked.connect(lambda: self.linkRequested.emit(self.f.id))
            hl.addWidget(self.link_btn)
            more = icon_button("more", "Mais ações", T.BLUE, 20)
            more.clicked.connect(lambda: self._menu(more, bool(others)))
            hl.addWidget(more)
        self.lay.addWidget(head)

        # ---------------- textos da avaliação inicial
        self.fields: dict[str, AutoText] = {}
        self.captions: dict[str, QWidget] = {}
        desc_label = lb.description_req if kind == "requerido" else lb.description_mel
        desc_ph = ("Descreva o ponto fraco encontrado" if kind == "requerido"
                   else "Descreva o que pode ser melhorado")
        self._text_block("description", desc_label, desc_ph, f.description, editable=edit)
        if kind == "requerido":
            self.lay.addWidget(separator(16))
            self._text_block("suggestion", lb.suggestion, "O que a empresa deve fazer para corrigir",
                             f.suggestion, editable=edit)

        # ---------------- impacto (só para REQUERIDO)
        # "Leve" muda a avaliação final: o resultado pode terminar em T mesmo sem correção, mas o problema
        # continua como ponto fraco (Guia de Avaliação 2024, Parte I, p. 58; ver rules.Snapshot.kept_as_weak).
        # Para MELHORIA o impacto não se aplica: a correção já fica a critério da empresa.
        self.impact = None
        self.impact_help = None
        if kind == "requerido":
            self.lay.addWidget(separator(16))
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(16, 8, 12, 8)
            rl.setSpacing(10)
            rl.addWidget(label("Impacto na avaliação", T.BODY), 1)
            self.impact = Segmented([Option(v, "—" if v == "-" else v.capitalize()) for v in lb.impact], min_seg=58)
            self.impact.set_value(f.impact if f.impact in lb.impact else lb.impact[0])
            self.impact.setEnabled(edit)
            self.impact.ratingChanged.connect(self._on_impact)
            rl.addWidget(self.impact)
            self.lay.addWidget(row)
            self.impact_help = label("Leve: na avaliação final o resultado pode ficar T mesmo sem correção; o problema "
                                     "continua registrado como ponto fraco (Guia de Avaliação, p. 58).",
                                     T.FOOTNOTE, color=T.SECONDARY, wrap=True)
            self.impact_help.setContentsMargins(16, 0, 16, 10)
            self.lay.addWidget(self.impact_help)
            self.impact_help.setVisible(f.impact == IMPACT_LEVE)

        # ---------------- avaliação final: correção da empresa
        self.status = None
        if final:
            self.lay.addWidget(separator(0))
            band = QWidget()
            band.setObjectName("FinalBand")
            band.setStyleSheet(f"#FinalBand {{ background: {T.BLUE_TINT}; }}")
            bl = QHBoxLayout(band)
            bl.setContentsMargins(16, 7, 16, 7)
            bl.setSpacing(6)
            bl.addWidget(label("Avaliação final", T.FOOTNOTE, QFont.Weight.DemiBold, T.BLUE_TEXT))
            bl.addStretch(1)
            if kind == "melhoria":
                bl.addWidget(label("Melhoria: a empresa decide se corrige", T.FOOTNOTE, color=T.BLUE_TEXT))
            elif f.impact == IMPACT_LEVE:
                bl.addWidget(label("Requerido leve: pode ficar T mesmo sem correção", T.FOOTNOTE,
                                   QFont.Weight.Medium, T.BLUE_TEXT))
            self.lay.addWidget(band)
            srow = QWidget()
            sl = QHBoxLayout(srow)
            sl.setContentsMargins(16, 9, 12, 9)
            sl.setSpacing(10)
            self.status_caption = label("Empresa realizou correção?", T.BODY)
            sl.addWidget(self.status_caption, 1)
            tones = {"Sim": "ok", "Não": "bad", "Sem Correção": "neutral"}
            self.status = Segmented([Option(v, "Sem correção" if v == "Sem Correção" else v, tones.get(v, "neutral"))
                                     for v in lb.correction], min_seg=64)
            self.status.set_value(f.correction_status)
            self.status.setEnabled(mode == "final")
            self.status.ratingChanged.connect(lambda v: self._emit_now("correction_status", v))
            sl.addWidget(self.status)
            self.lay.addWidget(srow)
            self.lay.addWidget(separator(16))
            self._text_block("correction_text", "Correção realizada",
                             "O que a empresa corrigiu e quais evidências apresentou", f.correction_text,
                             editable=mode == "final")
        self._loading = False

    # ------------------------------------------------------------ construção
    def _text_block(self, key: str, caption: str, placeholder: str, value: str, editable: bool):
        cap = label(caption.upper(), T.CAPTION, QFont.Weight.DemiBold, T.SECONDARY)
        cap.setContentsMargins(16, 10, 16, 0)
        self.lay.addWidget(cap)
        self.captions[key] = cap
        ed = AutoText(placeholder if editable else "—", 60 if editable else 30)
        ed.setPlainText(value)
        ed.setReadOnly(not editable)
        if not editable:
            ed.setStyleSheet(f"color: {T.LABEL_2};")
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(12, 0, 12, 6)
        wl.addWidget(ed)
        self.lay.addWidget(wrap)
        self.fields[key] = ed
        if editable:
            t = QTimer(self, singleShot=True, interval=450)
            t.timeout.connect(lambda k=key: self._emit_text(k))
            self._timers[key] = t
            ed.textChanged.connect(lambda: None if self._loading else t.start())

    def _menu(self, anchor, shared: bool):
        m = QMenu(self)
        if shared:
            m.addAction(T.icon("x", T.LABEL_2, 16), "Desvincular deste resultado",
                        lambda: self.unlinkRequested.emit(self.f.id))
        m.addAction(T.icon("trash", T.RED, 16), "Excluir apontamento", lambda: self.deleteRequested.emit(self.f.id))
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    # ------------------------------------------------------------ emissão
    def _emit_text(self, key: str):
        self.edited.emit(self.f.id, key, self.fields[key].toPlainText())

    def _on_impact(self, v):
        if v is None:                      # Delete no controle: volta ao padrão, o campo nunca fica vazio
            v = self.model.labels.impact[0]
            self.impact.set_value(v)
        if self.impact_help is not None:
            self.impact_help.setVisible(v == IMPACT_LEVE)
        self._emit_now("impact", v)

    def _emit_now(self, key: str, value):
        if not self._loading:
            self.edited.emit(self.f.id, key, value)

    def flush(self):
        for k, t in self._timers.items():
            if t.isActive():
                t.stop()
                self._emit_text(k)

    # ------------------------------------------------------------ estado
    def update_from(self, f: Finding):
        """Atualiza valores não textuais vindos do banco, sem tocar no que está sendo digitado."""
        self.f = f
        self._loading = True
        if self.status is not None and self.status.value() != f.correction_status:
            self.status.set_value(f.correction_status)
        if self.impact is not None and self.impact.value() != f.impact:
            self.impact.set_value(f.impact)
        self._loading = False

    def set_missing(self, keys: set[str]):
        self.set_invalid(bool(keys))
        for k, cap in self.captions.items():
            cap.setStyleSheet(f"color: {T.TONE_TEXT['warn'] if k in keys else T.SECONDARY}; background: transparent;")
        if self.status is not None:
            col = T.TONE_TEXT["warn"] if "correction_status" in keys else T.LABEL
            self.status_caption.setStyleSheet(f"color: {col}; background: transparent;")

    def focus_first(self, keys: set[str] | None = None):
        for k, ed in self.fields.items():
            if not ed.isReadOnly() and (keys is None or k in keys):
                ed.setFocus()
                return True
        return False

    def missing_keys(self, snap: Snapshot, cid: str) -> set[str]:
        f = self.f
        out: set[str] = set()
        if self.mode == "edit":
            if not f.description.strip():
                out.add("description")
            if snap.item_kind(cid) == "requerido" and self.kind == "requerido" and not f.suggestion.strip():
                out.add("suggestion")
        elif self.mode == "final":
            if not f.correction_status:
                out.add("correction_status")
            elif f.correction_status == "Sim" and not f.correction_text.strip():
                out.add("correction_text")
        return out


class LinkDialog(QDialog):
    """Escolhe outros resultados do mesmo processo que compartilham o apontamento."""

    def __init__(self, model: NormModel, snap: Snapshot, f: Finding, current: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aplicar apontamento")
        self.setModal(True)
        self.setMinimumSize(560, 600)
        self.current = current
        kind = snap.finding_kind(f) or snap.item_kind(current)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("NavBar")
        bar.setFixedHeight(54)
        bl = QGridLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        cancel = button("Cancelar", "ghost")
        cancel.setFont(T.font(T.BODY))
        cancel.clicked.connect(self.reject)
        bl.addWidget(cancel, 0, 0, Qt.AlignmentFlag.AlignLeft)
        bl.addWidget(label("Aplicar também a", T.HEADLINE + 0.5, QFont.Weight.DemiBold), 0, 1,
                     Qt.AlignmentFlag.AlignCenter)
        self.ok = button("Aplicar", "ghost")
        self.ok.setFont(T.font(T.BODY, QFont.Weight.DemiBold))
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        bl.addWidget(self.ok, 0, 2, Qt.AlignmentFlag.AlignRight)
        bl.setColumnStretch(0, 1)
        bl.setColumnStretch(2, 1)
        lay.addWidget(bar)

        content = QWidget()
        content.setObjectName("Page")
        body = QVBoxLayout(content)
        body.setContentsMargins(20, 18, 20, 24)
        body.setSpacing(0)
        proc = model.process(f.process)
        cur = model.criterion(current)
        want = "P ou N" if kind == "requerido" else "L"
        intro = label(f"O apontamento de {cur.code} passa a valer para os resultados marcados, com o mesmo texto. "
                      f"Só é possível juntar resultados de {proc.code} caracterizados como {want}.",
                      T.CALLOUT, color=T.LABEL_2, wrap=True)
        intro.setContentsMargins(16, 0, 16, 0)
        body.addWidget(intro)
        body.addSpacing(16)

        self.rows: dict[str, SelectRow] = {}
        for gname, items in proc.groups:
            group = [c for c in items if c.id != current]
            if not group:
                continue
            body.addWidget(SectionHeader(gname))
            body.addSpacing(6)
            card = Card()
            rows = []
            for c in group:
                r = snap.initial(c.id)
                linked = c.id in f.items
                compatible = bool(r and r.finding and ((r.finding == "requerido") == (kind == "requerido")))
                row = SelectRow(checked=linked, enabled=compatible or linked)
                code = label(c.code, T.BODY, QFont.Weight.DemiBold, T.LABEL if (compatible or linked) else T.TERTIARY)
                code.setFixedWidth(70)
                row.lay.addWidget(code)
                row.lay.addWidget(label(c.title, T.BODY, color=T.LABEL_2 if (compatible or linked) else T.TERTIARY), 1)
                if r:
                    row.lay.addWidget(label(r.code, T.FOOTNOTE, QFont.Weight.Bold,
                                            T.TONE_TEXT[r.tone] if compatible or linked else T.TERTIARY))
                else:
                    row.lay.addWidget(label("sem nota", T.FOOTNOTE, color=T.TERTIARY))
                if not (compatible or linked):
                    row.setToolTip(f"Caracterize como {want} para juntar a este apontamento")
                row.finish()
                rows.append(row)
                self.rows[c.id] = row
            grouped_rows(card, rows, inset=50)
            body.addWidget(card)
            body.addSpacing(18)
        body.addWidget(section_footer("Para desfazer depois, use “Desvincular deste resultado” no apontamento."))
        body.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(content)
        lay.addWidget(sc, 1)

    def selected(self) -> list[str]:
        return [self.current] + [cid for cid, r in self.rows.items() if r.is_checked()]

    def sizeHint(self):
        return QSize(600, 680)
