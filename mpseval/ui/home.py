"""Tela inicial: lista de avaliações, criação e retomada."""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                             QScrollArea, QVBoxLayout, QWidget)

from ..core import report, rules
from ..core.model import NormModel
from ..core.storage import Assessment, Store
from . import theme as T
from .widgets import (Card, ProgressRing, Row, SectionHeader, button, chip, clear_layout, grouped_rows,
                      icon_button, label, section_footer, separator)


def relative(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    delta = datetime.now() - dt
    if delta.days == 0:
        mins = int(delta.total_seconds() // 60)
        if mins < 1:
            return "agora há pouco"
        if mins < 60:
            return f"há {mins} min"
        return f"hoje, {dt:%H:%M}"
    if delta.days == 1:
        return f"ontem, {dt:%H:%M}"
    return dt.strftime("%d/%m/%Y")


class AssessmentDialog(QDialog):
    """Folha (sheet) de criação ou edição: Cancelar à esquerda, título ao centro, ação à direita."""

    def __init__(self, model: NormModel, parent=None, a: Assessment | None = None):
        super().__init__(parent)
        self.setWindowTitle("Editar dados" if a else "Nova avaliação")
        self.setModal(True)
        self.setMinimumWidth(500)
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
        bl.addWidget(label("Editar avaliação" if a else "Nova avaliação", T.HEADLINE + 0.5, QFont.Weight.DemiBold),
                     0, 1, Qt.AlignmentFlag.AlignCenter)
        self.ok = button("Salvar" if a else "Criar", "ghost")
        self.ok.setFont(T.font(T.BODY, QFont.Weight.DemiBold))
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._submit)
        bl.addWidget(self.ok, 0, 2, Qt.AlignmentFlag.AlignRight)
        bl.setColumnStretch(0, 1)
        bl.setColumnStretch(2, 1)
        lay.addWidget(bar)

        body = QVBoxLayout()
        body.setContentsMargins(20, 22, 20, 22)
        body.setSpacing(0)
        body.addWidget(SectionHeader("Identificação"))
        body.addSpacing(6)
        card = Card()
        settings = QSettings()
        self.fields: dict[str, QLineEdit] = {}
        rows = []
        for key, title, ph in (("organization", "Organização", "Empresa avaliada"),
                               ("project", "Projeto", "Nome do projeto"),
                               ("evaluator", "Avaliador(a)", "Seu nome")):
            r = QWidget()
            rl = QHBoxLayout(r)
            rl.setContentsMargins(16, 4, 12, 4)
            rl.setSpacing(12)
            t = label(title, T.BODY)
            t.setFixedWidth(108)
            rl.addWidget(t)
            e = QLineEdit()
            e.setProperty("role", "cell")
            e.setFont(T.font(T.BODY))
            e.setPlaceholderText(ph)
            e.setMinimumHeight(36)
            if a:
                e.setText(getattr(a, key))
            elif key == "evaluator":
                e.setText(settings.value("last_evaluator", ""))
            e.textChanged.connect(self._validate)
            e.returnPressed.connect(self._submit)
            rl.addWidget(e, 1)
            rows.append(r)
            self.fields[key] = e
        for i, r in enumerate(rows):
            if i:
                card.lay.addWidget(separator(16))
            card.lay.addWidget(r)
        body.addWidget(card)
        body.addSpacing(6)
        body.addWidget(section_footer(f"{model.name}. Nível {model.level}: GPR, REQ e capacidade dos processos de "
                                      f"projeto ({len(model.criteria)} itens)."))
        lay.addLayout(body)
        self._validate()
        self.fields["organization"].setFocus()

    def _validate(self):
        self.ok.setEnabled(all(e.text().strip() for e in self.fields.values()))

    def _submit(self):
        if not self.ok.isEnabled():
            empty = next(e for e in self.fields.values() if not e.text().strip())
            empty.setFocus()
            return
        QSettings().setValue("last_evaluator", self.fields["evaluator"].text().strip())
        self.accept()

    def values(self) -> dict[str, str]:
        return {k: e.text().strip() for k, e in self.fields.items()}


class AssessmentRow(Row):
    openRequested = pyqtSignal(int)
    editRequested = pyqtSignal(int)
    deleteRequested = pyqtSignal(int)
    exportRequested = pyqtSignal(int, str)

    def __init__(self, a: Assessment, done: int, total: int):
        super().__init__(chevron=True)
        self.aid = a.id
        self.lay.setContentsMargins(14, 12, 12, 12)
        self.lay.setSpacing(14)
        ring = ProgressRing(40)
        ring.set(done / total if total else 0, f"{round(100 * done / total) if total else 0}%")
        self.lay.addWidget(ring)

        txt = QVBoxLayout()
        txt.setSpacing(2)
        txt.addWidget(label(a.organization, T.HEADLINE + 0.5, QFont.Weight.DemiBold))
        txt.addWidget(label(f"{a.project}  ·  {a.evaluator}", T.SUBHEAD, color=T.SECONDARY))
        holder = QWidget()
        holder.setLayout(txt)
        self.lay.addWidget(holder, 1)

        meta = QGridLayout()
        meta.setHorizontalSpacing(26)
        meta.setVerticalSpacing(1)
        for col, (k, v, w) in enumerate((("Revisitas" if a.in_final else "Itens", f"{done} de {total}", 64),
                                         ("Tempo", report.fmt_duration(a.total_elapsed), 64),
                                         ("Atualizada", relative(a.updated_at), 104))):
            meta.addWidget(label(k, T.CAPTION, color=T.SECONDARY), 0, col)
            meta.addWidget(label(v, T.SUBHEAD, QFont.Weight.Medium, T.LABEL_2), 1, col)
            meta.setColumnMinimumWidth(col, w)
        mh = QWidget()
        mh.setLayout(meta)
        self.lay.addWidget(mh)

        if a.completed:
            c = chip("Concluída", T.TONE_TEXT["ok"], T.TONE_SOFT["ok"])
        elif a.in_final:
            c = chip("Avaliação final", T.BLUE_TEXT, T.BLUE_TINT)
        elif a.finished:
            c = chip("Inicial concluída", T.TONE_TEXT["ok"], T.TONE_SOFT["ok"])
        else:
            c = chip("Em andamento", T.LABEL_2, T.FILL_CARD)
        c.setFixedWidth(118)
        self.lay.addWidget(c, 0, Qt.AlignmentFlag.AlignVCenter)

        more = icon_button("more", "Mais ações", T.BLUE, 20)
        more.clicked.connect(self._menu)
        self._more = more
        self.lay.addWidget(more)
        self.finish()
        self.clicked.connect(lambda: self.openRequested.emit(self.aid))

    def _menu(self):
        m = QMenu(self)
        m.addAction(T.icon("edit", T.LABEL_2, 16), "Editar dados", lambda: self.editRequested.emit(self.aid))
        m.addAction(T.icon("share", T.LABEL_2, 16), "Exportar relatório de ajustes (XLSX)",
                    lambda: self.exportRequested.emit(self.aid, "xlsx"))
        m.addAction(T.icon("share", T.LABEL_2, 16), "Exportar PDF", lambda: self.exportRequested.emit(self.aid, "pdf"))
        m.addAction(T.icon("share", T.LABEL_2, 16), "Exportar CSV", lambda: self.exportRequested.emit(self.aid, "csv"))
        m.addSeparator()
        m.addAction(T.icon("trash", T.RED, 16), "Excluir avaliação", lambda: self.deleteRequested.emit(self.aid))
        m.exec(self._more.mapToGlobal(self._more.rect().bottomLeft()))


class HomeView(QWidget):
    openRequested = pyqtSignal(int)
    exportRequested = pyqtSignal(int, str)

    def __init__(self, store: Store, model: NormModel, parent=None):
        super().__init__(parent)
        self.store, self.model = store, model
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        holder = QWidget()
        holder.setObjectName("Page")
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addStretch(1)
        self.content = QWidget()
        self.content.setMaximumWidth(960)
        hl.addWidget(self.content, 100)
        hl.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(holder)
        root.addWidget(sc)

        L = QVBoxLayout(self.content)
        L.setContentsMargins(36, 36, 36, 40)
        L.setSpacing(0)

        top = QHBoxLayout()
        top.setContentsMargins(4, 0, 0, 0)
        app_icon = QLabel()
        app_icon.setPixmap(T.app_icon().pixmap(44, 44))
        app_icon.setStyleSheet("background: transparent;")
        top.addWidget(app_icon, 0, Qt.AlignmentFlag.AlignTop)
        top.addSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Avaliações", T.LARGE_TITLE + 6, QFont.Weight.Bold, display=True))
        titles.addWidget(label(f"MPS.BR Nível {model.level} ({model.level_name}) · Gerência de Projetos e "
                               "Engenharia de Requisitos", T.SUBHEAD, color=T.SECONDARY, wrap=True))
        top.addLayout(titles, 1)
        top.addSpacing(16)
        self.new_btn = button("Nova avaliação", "primary", "plus")
        self.new_btn.setMinimumHeight(36)
        self.new_btn.setToolTip("Ctrl+N")
        self.new_btn.clicked.connect(self.new_assessment)
        top.addWidget(self.new_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        L.addLayout(top)
        L.addSpacing(18)

        self.search = QLineEdit()
        self.search.setProperty("role", "search")
        self.search.setPlaceholderText("Buscar por organização, projeto ou avaliador")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(36)
        self.search.addAction(T.icon("search", T.SECONDARY, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.refresh)
        L.addWidget(self.search)
        L.addSpacing(22)

        self.header = SectionHeader("")
        L.addWidget(self.header)
        L.addSpacing(6)
        self.list = QVBoxLayout()
        self.list.setSpacing(0)
        L.addLayout(self.list)
        L.addStretch(1)
        self.refresh()

    def refresh(self):
        clear_layout(self.list)
        items = self.store.list()
        q = self.search.text().strip().lower()
        shown = [a for a in items if not q or q in f"{a.organization} {a.project} {a.evaluator}".lower()]
        self.search.setVisible(bool(items))
        self.header.setVisible(bool(items))
        n = len(items)
        done = sum(1 for a in items if a.completed or (a.finished and not a.in_final))
        self.header.title.setText("Recentes")
        self.header.set_aside(f"{n} {'avaliação' if n == 1 else 'avaliações'} · {done} "
                              f"{'concluída' if done == 1 else 'concluídas'}" if n else "")
        if not items:
            self.list.addWidget(self._empty())
            return
        if not shown:
            card = Card(padding=(16, 14, 16, 14))
            card.lay.addWidget(label("Nenhuma avaliação corresponde à busca.", T.BODY, color=T.SECONDARY))
            self.list.addWidget(card)
            return
        card = Card()
        rows = []
        for a in shown:
            prog = rules.load(self.model, self.store, a.id).progress()
            row = AssessmentRow(a, prog.done, prog.total)
            row.openRequested.connect(self.openRequested.emit)
            row.editRequested.connect(self.edit_assessment)
            row.deleteRequested.connect(self.delete_assessment)
            row.exportRequested.connect(self.exportRequested.emit)
            rows.append(row)
        grouped_rows(card, rows, inset=68)
        self.list.addWidget(card)

    def _empty(self) -> QWidget:
        card = Card(padding=(32, 44, 32, 44), spacing=8)
        ic = QLabel()
        ic.setPixmap(T.app_icon().pixmap(64, 64))
        ic.setStyleSheet("background: transparent;")
        card.lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
        card.lay.addSpacing(6)
        card.lay.addWidget(label("Nenhuma avaliação ainda", T.TITLE_2, QFont.Weight.DemiBold, display=True), 0,
                           Qt.AlignmentFlag.AlignHCenter)
        msg = label(f"Crie uma avaliação para percorrer os {len(self.model.criteria)} itens de GPR, REQ e CP-Proj, "
                    "registrar evidências e gerar o Relatório de Ajustes.", T.BODY, color=T.SECONDARY, wrap=True)
        msg.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        card.lay.addWidget(msg)
        card.lay.addSpacing(10)
        b = button("Nova avaliação", "primary", "plus")
        b.setMinimumHeight(36)
        b.clicked.connect(self.new_assessment)
        card.lay.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        return card

    def new_assessment(self):
        dlg = AssessmentDialog(self.model, self)
        if dlg.exec():
            v = dlg.values()
            a = self.store.create(v["organization"], v["project"], v["evaluator"], self.model)
            self.refresh()
            self.openRequested.emit(a.id)

    def edit_assessment(self, aid: int):
        dlg = AssessmentDialog(self.model, self, self.store.get(aid))
        if dlg.exec():
            v = dlg.values()
            self.store.update_info(aid, v["organization"], v["project"], v["evaluator"])
            self.refresh()

    def delete_assessment(self, aid: int):
        a = self.store.get(aid)
        box = QMessageBox(self)
        box.setWindowTitle("Excluir avaliação")
        box.setText(f"Excluir a avaliação de {a.organization} / {a.project}?")
        box.setInformativeText("Caracterizações, evidências e histórico serão apagados. Esta ação não pode ser desfeita.")
        yes = box.addButton("Excluir", QMessageBox.ButtonRole.DestructiveRole)
        yes.setProperty("variant", "danger")
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.store.delete(aid)
            self.refresh()
