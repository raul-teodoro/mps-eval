"""Área de trabalho de uma avaliação: navegação, edição guiada, cronômetro e revisão."""
from __future__ import annotations

import time
from datetime import datetime

from PyQt6.QtCore import QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMessageBox, QScrollArea,
                             QStackedWidget, QVBoxLayout, QWidget)

from ..core import report, rules
from ..core.model import NormModel
from ..core.storage import Store
from . import theme as T
from .editor import EDIT, FINAL, FINAL_FIXED, FINAL_LOCKED, LOCKED, ItemEditor
from .export import export_dialog
from .findings import LinkDialog
from .review import ReviewPage
from .sidebar import Sidebar
from .widgets import ProgressBar, Toast, button, fade_in, icon_button, label, set_variant


def _centered_scroll(content: QWidget, max_width: int = 820) -> QScrollArea:
    holder = QWidget()
    h = QHBoxLayout(holder)
    h.setContentsMargins(0, 0, 0, 0)
    h.addStretch(1)
    content.setMaximumWidth(max_width)
    h.addWidget(content, 100)
    h.addStretch(1)
    holder.setObjectName("Page")
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.Shape.NoFrame)
    sc.setWidget(holder)
    return sc


class Workspace(QWidget):
    backRequested = pyqtSignal()
    changed = pyqtSignal()

    def __init__(self, store: Store, model: NormModel, assessment_id: int, parent=None):
        super().__init__(parent)
        self.store, self.model, self.aid = store, model, assessment_id
        self.a = store.get(assessment_id)
        self.snap = rules.load(model, store, assessment_id)
        self._kept = self._kept_ids()      # resultados em T pela regra do requerido leve

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = Sidebar(model)
        self.sidebar.itemSelected.connect(self.open_item)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        # página do item
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        self.banner = self._build_banner()
        pl.addWidget(self.banner)
        self.editor = ItemEditor(model)
        self.editor.ratingChanged.connect(self._on_rating)
        self.editor.finalRatingChanged.connect(self._on_final_rating)
        self.editor.evidenceAdded.connect(self._on_evidence_added)
        self.editor.evidenceRemoved.connect(self._on_evidence_removed)
        self.editor.findingEdited.connect(self._on_finding_edited)
        self.editor.findingAddRequested.connect(self._on_finding_add)
        self.editor.findingLinkRequested.connect(self._on_finding_link)
        self.editor.findingUnlinkRequested.connect(self._on_finding_unlink)
        self.editor.findingDeleteRequested.connect(self._on_finding_delete)
        self.editor_scroll = _centered_scroll(self.editor, 860)
        pl.addWidget(self.editor_scroll, 1)
        pl.addWidget(self._build_footer())
        self.stack.addWidget(page)
        # página de revisão
        self.review = ReviewPage(model)
        self.review.jumpTo.connect(self.open_item)
        self.review.finalizeRequested.connect(self._finalize)
        self.review.reopenRequested.connect(self._reopen)
        self.review.startFinalRequested.connect(self._start_final)
        self.review.backToInitialRequested.connect(self._back_to_initial)
        self.review.exportRequested.connect(self.export)
        self.review_scroll = _centered_scroll(self.review, 860)
        self.stack.addWidget(self.review_scroll)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self.toast = Toast(self)
        self._install_shortcuts()

        # cronômetro de avaliação (métrica de tempo do teste A/B)
        self._elapsed = self.a.phase_elapsed
        self._unsaved_secs = 0
        self._paused = False
        self._last_tick = time.monotonic()
        self._tick = QTimer(self, interval=1000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        QGuiApplication.instance().applicationStateChanged.connect(self._on_app_state)

        self._refresh_all()
        start = self.a.current_item if self.a.current_item in self.order else self._first_open_item()
        self.open_item(start, animate=False)

    @property
    def order(self) -> list[str]:
        """Itens percorridos na fase atual (na avaliação final, só os que têm apontamento)."""
        return self.snap.scope() or [c.id for c in self.model.criteria]

    @property
    def answers(self):
        return self.snap.answers

    def mode_for(self, cid: str) -> str:
        if not self.a.in_final:
            return LOCKED if self.a.finished else EDIT
        if not self.snap.revisit(cid):
            return FINAL_FIXED
        return FINAL_LOCKED if self.a.finished else FINAL

    # ================================================================ construção
    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("NavBar")
        bar.setFixedHeight(60)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 0, 16, 0)
        lay.setSpacing(10)
        back = button("Avaliações", "ghost", "chevron-left")
        back.setIcon(T.icon("chevron-left", T.BLUE, 18, 2.4))
        back.setFont(T.font(T.BODY))
        back.setToolTip("Voltar à lista de avaliações (Esc)")
        back.clicked.connect(self._go_back)
        lay.addWidget(back)
        lay.addSpacing(6)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.t_title = label("", T.HEADLINE + 0.5, QFont.Weight.DemiBold)
        self.t_sub = label("", T.FOOTNOTE, color=T.SECONDARY)
        names.addStretch(1)
        names.addWidget(self.t_title)
        names.addWidget(self.t_sub)
        names.addStretch(1)
        lay.addLayout(names)
        lay.addStretch(1)

        prog = QVBoxLayout()
        prog.setSpacing(5)
        prog.addStretch(1)
        self.p_text = label("", T.FOOTNOTE, QFont.Weight.Medium, T.SECONDARY)
        prog.addWidget(self.p_text)
        self.p_bar = ProgressBar(4)
        self.p_bar.setFixedWidth(200)
        prog.addWidget(self.p_bar)
        prog.addStretch(1)
        lay.addLayout(prog)
        lay.addSpacing(8)

        self.timer_btn = button("00:00:00", "", "clock")
        self.timer_btn.setFont(T.font(T.CALLOUT, QFont.Weight.DemiBold))
        self.timer_btn.clicked.connect(self.toggle_pause)
        self.timer_btn.setFixedWidth(176)
        lay.addWidget(self.timer_btn)

        self.saved_lbl = label("", T.FOOTNOTE, color=T.SECONDARY)
        self.saved_lbl.setFixedWidth(44)
        self._saved_timer = QTimer(self, singleShot=True, interval=1800)
        self._saved_timer.timeout.connect(lambda: self.saved_lbl.setText(""))
        lay.addWidget(self.saved_lbl)

        keys = icon_button("keyboard", "Atalhos de teclado (F1)", T.BLUE, 20)
        keys.clicked.connect(self.show_shortcuts)
        lay.addWidget(keys)

        self.review_btn = button("Revisar e concluir", "")
        self.review_btn.setMinimumHeight(32)
        self.review_btn.clicked.connect(self.show_review)
        lay.addWidget(self.review_btn)
        return bar

    def _build_banner(self) -> QWidget:
        f = QFrame()
        f.setObjectName("Banner")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(20, 6, 12, 6)
        lay.setSpacing(8)
        self.banner_icon = QLabel()
        self.banner_icon.setStyleSheet("background: transparent;")
        lay.addWidget(self.banner_icon)
        self.banner_lbl = label("", T.CALLOUT, QFont.Weight.Medium, T.TONE_TEXT["ok"])
        lay.addWidget(self.banner_lbl)
        lay.addStretch(1)
        self.banner_btn2 = button("", "ghost")
        self.banner_btn2.clicked.connect(self._start_final)
        lay.addWidget(self.banner_btn2)
        self.banner_btn = button("", "ghost")
        self.banner_btn.clicked.connect(self._reopen)
        lay.addWidget(self.banner_btn)
        f.hide()
        return f

    def _refresh_banner(self):
        a = self.a
        n = len(self.snap.revisit_ids())
        if not a.in_final and not a.finished:
            self.banner.hide()
            return
        if a.in_final and not a.finished:
            tone_bg, tone_fg, ic, ic_col = T.BLUE_TINT, T.BLUE_TEXT, "wrench", T.BLUE
            text = (f"Avaliação final: registre a correção da empresa e a nova caracterização dos {n} "
                    f"{'resultado' if n == 1 else 'resultados'} com apontamento.")
            self.banner_btn.hide()
            self.banner_btn2.hide()
        elif a.in_final:
            tone_bg, tone_fg, ic, ic_col = T.TONE_SOFT["ok"], T.TONE_TEXT["ok"], "check-circle", T.GREEN
            text = "Avaliação concluída (inicial e final). Os registros estão bloqueados para edição."
            self.banner_btn.setText("Reabrir avaliação final")
            self.banner_btn.show()
            self.banner_btn2.hide()
        else:
            tone_bg, tone_fg, ic, ic_col = T.TONE_SOFT["ok"], T.TONE_TEXT["ok"], "check-circle", T.GREEN
            text = "Avaliação inicial concluída. Os registros estão bloqueados para edição."
            self.banner_btn.setText("Reabrir")
            self.banner_btn.show()
            self.banner_btn2.setText("Iniciar avaliação final")
            self.banner_btn2.setVisible(n > 0)
        self.banner.setStyleSheet(f"#Banner {{ background: {tone_bg}; border-bottom: 1px solid {T.SEPARATOR}; }}")
        self.banner_icon.setPixmap(T.icon(ic, ic_col, 18, 2.0).pixmap(18, 18))
        self.banner_lbl.setText(text)
        self.banner_lbl.setStyleSheet(f"color: {tone_fg}; background: transparent;")
        self.banner.show()

    def _build_footer(self) -> QWidget:
        f = QFrame()
        f.setObjectName("Toolbar")
        f.setFixedHeight(60)
        lay = QHBoxLayout(f)
        lay.setContentsMargins(12, 0, 16, 0)
        lay.setSpacing(10)
        self.prev_btn = button("Anterior", "ghost")
        self.prev_btn.setIcon(T.icon("chevron-left", T.BLUE, 18, 2.4))
        self.prev_btn.setFont(T.font(T.BODY))
        self.prev_btn.setToolTip("Item anterior (Ctrl+↑)")
        self.prev_btn.clicked.connect(lambda: self.step(-1))
        lay.addWidget(self.prev_btn)
        lay.addStretch(1)
        self.state_icon = QLabel()
        self.state_icon.setStyleSheet("background: transparent;")
        lay.addWidget(self.state_icon)
        self.state_lbl = label("", T.CALLOUT, QFont.Weight.Medium)
        lay.addWidget(self.state_lbl)
        lay.addStretch(1)
        self.pending_btn = button("", "ghost")
        self.pending_btn.clicked.connect(self.next_pending)
        lay.addWidget(self.pending_btn)
        self.next_btn = button("Próximo", "primary")
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_btn.setIcon(T.icon("chevron-right", "#FFFFFF", 16, 2.4))
        self.next_btn.setIconSize(QSize(16, 16))
        self.next_btn.setMinimumWidth(140)
        self.next_btn.setMinimumHeight(36)
        self.next_btn.clicked.connect(self.next_or_review)
        lay.addWidget(self.next_btn)
        return f

    def _install_shortcuts(self):
        ctx = Qt.ShortcutContext.WidgetWithChildrenShortcut

        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(ctx)
            s.activated.connect(fn)

        for i, r in enumerate(self.model.final_scale, start=1):
            sc(str(i), lambda code=r.code: self._rate_key(code))
            sc(f"Alt+{i}", lambda code=r.code: self._rate_key(code))
        sc("Ctrl+Shift+Return", self.next_pending)
        sc("Ctrl+Shift+Enter", self.next_pending)
        sc("Ctrl+Z", self.undo_remove)
        sc("F1", self.show_shortcuts)
        sc("Ctrl+Return", self.next_or_review)
        sc("Ctrl+Enter", self.next_or_review)
        sc("Ctrl+Down", lambda: self.step(1))
        sc("Ctrl+Up", lambda: self.step(-1))
        sc("Ctrl+F", lambda: (self.sidebar.search.setFocus(), self.sidebar.search.selectAll()))
        sc("Ctrl+E", self.editor.focus_evidence)
        sc("Ctrl+R", self.show_review)
        sc("Ctrl+P", self.toggle_pause)
        sc("Escape", self._escape)

    # ================================================================ navegação
    def _first_open_item(self) -> str:
        for cid in self.order:
            if not self.snap.check(cid).done:
                return cid
        return self.order[0]

    def open_item(self, cid: str, animate: bool = True):
        if not self.model.has(cid):
            return
        self.editor.flush()
        self.stack.setCurrentIndex(0)
        order = self.order
        pos = f"Item {order.index(cid) + 1} de {len(order)}" if cid in order else ""
        if self.a.in_final and cid in order:
            pos = f"Revisita {order.index(cid) + 1} de {len(order)}"
        self.editor.show_item(self.model.criterion(cid), self.snap, self.mode_for(cid), pos)
        self.sidebar.select(cid)
        self.editor_scroll.verticalScrollBar().setValue(0)
        if self.mode_for(cid) in (FINAL, FINAL_LOCKED):
            QTimer.singleShot(40, self._scroll_to_findings)    # na revisita, o foco é o apontamento
        self.store.set_current(self.aid, cid)
        self._refresh_footer()
        if animate:
            fade_in(self.editor, 140, 0.35)

    def _scroll_to_findings(self):
        sec = self.editor.find_section
        if sec.isVisible() and self.stack.currentIndex() == 0:
            y = sec.mapTo(self.editor_scroll.widget(), QPoint(0, 0)).y()
            self.editor_scroll.verticalScrollBar().setValue(max(0, y - 60))

    def current(self) -> str | None:
        return self.editor.cid

    def _index(self, cid: str | None) -> int:
        order = self.order
        if cid in order:
            return order.index(cid)
        if cid is None:
            return -1
        # item fora do escopo (ex.: aberto pela revisão): posição pela ordem do modelo
        pos = self.model.order(cid)
        return sum(1 for c in order if self.model.order(c) < pos) - 0.5

    def step(self, delta: int):
        order = self.order
        if self.stack.currentIndex() == 1:
            if delta < 0:
                self.open_item(order[-1])
            return
        i = self._index(self.current())
        j = int(i + delta) if float(i).is_integer() else int(i + (0.5 if delta > 0 else -0.5))
        if 0 <= j < len(order):
            self.open_item(order[j])

    def next_or_review(self):
        if self.stack.currentIndex() == 1:
            return
        cid = self.current()
        done = self.snap.check(cid).done
        if not done and self.mode_for(cid) in (EDIT, FINAL):
            self.toast.show_message(self._missing_text(cid))
            return
        order = self.order
        i = self._index(cid)
        nxt = int(i) + 1 if float(i).is_integer() else int(i + 0.5)
        if nxt < len(order):
            self.open_item(order[nxt])
        else:
            self.show_review()

    def _pending_ids(self) -> list[str]:
        return [cid for cid in self.order if not self.snap.check(cid).done]

    def next_pending(self):
        pend = self._pending_ids()
        if not pend:
            self.show_review()
            return
        cur = self._index(self.current())
        after = [c for c in pend if self.order.index(c) > cur]
        self.open_item((after or pend)[0])

    def show_shortcuts(self):
        from .dialogs import ShortcutsDialog
        ShortcutsDialog(self).exec()

    def show_review(self):
        self.editor.flush()
        self.review.render(self.store.get(self.aid), self.snap)
        self.stack.setCurrentIndex(1)
        self.review_scroll.verticalScrollBar().setValue(0)
        fade_in(self.review, 160, 0.3)

    def _escape(self):
        if self.sidebar.search.hasFocus() and self.sidebar.search.text():
            self.sidebar.search.clear()
        elif self.stack.currentIndex() == 1:
            self.open_item(self.current() or self.order[0])
        else:
            self._go_back()

    def _go_back(self):
        self.flush()
        self.backRequested.emit()

    # ================================================================ edição
    def _guard(self) -> bool:
        """Permite alterar a avaliação inicial."""
        if self.a.in_final:
            self.toast.show_message("Na avaliação final, registre a correção e a nova caracterização.")
            return False
        if self.a.finished:
            self.toast.show_message("Avaliação inicial concluída. Reabra para alterar.")
            return False
        return True

    def _guard_final(self) -> bool:
        if not self.a.in_final:
            return False
        if self.a.finished:
            self.toast.show_message("Avaliação concluída. Reabra a avaliação final para alterar.")
            return False
        return True

    def _rate_key(self, code: str):
        if self.stack.currentIndex() != 0:
            return
        cid = self.current()
        if self.a.in_final:
            if self.mode_for(cid) == FINAL:
                self.editor.final_rating.select(code)
            elif self.mode_for(cid) == FINAL_FIXED:
                self.toast.show_message("Este resultado não tem apontamento e mantém a nota inicial.")
            else:
                self._guard_final()
        elif code in [r.code for r in self.model.scale] and self._guard():
            self.editor.rating.select(code)

    def _on_rating(self, cid: str, code):
        if not self._guard():
            self.editor.rating.set_value(self.snap.answer(cid).rating)
            return
        self.store.set_rating(self.aid, cid, code)
        self._sync_findings(cid)
        self._reload(cid, structural=True)
        if code:
            ans = self.snap.answer(cid)
            if not ans.evidences:
                self.editor.focus_evidence()
            elif self.snap.item_kind(cid):
                self.editor.focus_finding(self.snap)

    def _sync_findings(self, cid: str):
        """Cria o apontamento quando a nota exige (L, P, N) e limpa os vazios quando deixa de exigir."""
        snap = rules.load(self.model, self.store, self.aid)
        fs = snap.item_findings(cid)
        if snap.item_kind(cid):
            if not fs:
                self.store.create_finding(self.aid, self.model.criterion(cid).process, [cid])
        else:
            for f in fs:
                if f.items == (cid,) and f.empty:
                    self.store.delete_finding(self.aid, f.id)

    def _on_final_rating(self, cid: str, code):
        if not self._guard_final():
            self.editor.final_rating.set_value(self.snap.answer(cid).final_rating)
            return
        self.store.set_final_rating(self.aid, cid, code)
        self._reload(cid)

    def _on_finding_edited(self, fid: int, field: str, value):
        final_field = field in ("correction_status", "correction_text")
        if not (self._guard_final() if final_field else self._guard()):
            return
        self.store.update_finding(self.aid, fid, **{field: value if value is not None else None})
        cid = self.current()
        if field == "correction_status" and value in ("Não", "Sem Correção"):
            # sem correção: a nova caracterização parte da nota inicial
            snap = rules.load(self.model, self.store, self.aid)
            f = next(x for x in snap.findings if x.id == fid)
            for item in snap.active_items(f):
                if not snap.answer(item).final_rating:
                    self.store.set_final_rating(self.aid, item, snap.answer(item).rating)
                    if item == cid:
                        self.editor.final_rating.set_value(snap.answer(item).rating)
                        self.toast.show_message(f"Nova caracterização mantida como {snap.answer(item).rating}", 1800)
        self._reload(cid)

    def _on_finding_add(self, cid: str):
        if not self._guard():
            return
        self.store.create_finding(self.aid, self.model.criterion(cid).process, [cid])
        self._reload(cid, structural=True)
        self.editor.focus_finding(self.snap)

    def _finding(self, fid: int):
        return next((f for f in self.snap.findings if f.id == fid), None)

    def _on_finding_link(self, fid: int):
        if not self._guard():
            return
        self.editor.flush()
        self.snap = rules.load(self.model, self.store, self.aid)
        f, cid = self._finding(fid), self.current()
        if f is None or cid is None:
            return
        dlg = LinkDialog(self.model, self.snap, f, cid, self)
        if not dlg.exec():
            return
        selected = dlg.selected()
        for item in selected:
            if item in f.items:
                continue
            for other in self.snap.item_findings(item):       # descarta o apontamento vazio do item juntado
                if other.items == (item,) and other.empty:
                    self.store.delete_finding(self.aid, other.id)
        self.store.set_finding_items(self.aid, fid, selected)
        added = [self.model.criterion(i).code for i in selected if i not in f.items]
        removed = [self.model.criterion(i).code for i in f.items if i not in selected]
        for item in removed:
            self._sync_findings(item)
        self._reload(cid, structural=True)
        if added:
            self.toast.show_message("Apontamento aplicado também a " + ", ".join(added))
        elif removed:
            self.toast.show_message("Desvinculado de " + ", ".join(removed))

    def _on_finding_unlink(self, fid: int):
        if not self._guard():
            return
        f, cid = self._finding(fid), self.current()
        if f is None or cid not in f.items:
            return
        self.editor.flush()
        self.store.set_finding_items(self.aid, fid, [i for i in f.items if i != cid])
        self.store.create_finding(self.aid, self.model.criterion(cid).process, [cid])
        self._reload(cid, structural=True)
        self.toast.show_message("Apontamento desvinculado. Este resultado ganhou um apontamento próprio.")

    def _on_finding_delete(self, fid: int):
        if not self._guard():
            return
        self.editor.flush()
        self.snap = rules.load(self.model, self.store, self.aid)
        f, cid = self._finding(fid), self.current()
        if f is None:
            return
        shared = [self.model.criterion(i).code for i in self.snap.active_items(f) if i != cid]
        if not f.empty or shared:
            box = QMessageBox(self)
            box.setWindowTitle("Excluir apontamento")
            box.setText("Excluir este apontamento?")
            box.setInformativeText(("Ele também será removido de " + ", ".join(shared) + ". ") if shared else
                                   "O texto registrado será apagado. ")
            yes = box.addButton("Excluir", QMessageBox.ButtonRole.DestructiveRole)
            yes.setProperty("variant", "danger")
            box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is not yes:
                return
        self.delete_finding(fid)

    def delete_finding(self, fid: int):
        f, cid = self._finding(fid), self.current()
        items = list(f.items) if f else []
        self.store.delete_finding(self.aid, fid)
        for item in items:
            self._sync_findings(item)
        self._reload(cid, structural=True)

    def _on_evidence_added(self, cid: str, kind: str, content: str):
        if not self._guard():
            return
        self.store.add_evidence(self.aid, cid, kind, content)
        self._reload(cid, evidences=True)

    def _on_evidence_removed(self, cid: str, eid: int):
        if not self._guard():
            return
        ans = self.answers.get(cid)
        ev = next((e for e in (ans.evidences if ans else []) if e.id == eid), None)
        self.store.remove_evidence(self.aid, cid, eid)
        self._undo = (cid, ev.kind, ev.content) if ev else None
        self._reload(cid, evidences=True)
        self.toast.show_message("Evidência removida. Ctrl+Z desfaz.", 3200)

    def undo_remove(self):
        if not getattr(self, "_undo", None) or not self._guard():
            return
        cid, kind, content = self._undo
        self._undo = None
        self.store.add_evidence(self.aid, cid, kind, content)
        if self.current() != cid:
            self.open_item(cid)
        self._reload(cid, evidences=True)
        self.toast.show_message("Evidência restaurada", 1600)

    def _kept_ids(self) -> set[str]:
        return {c for c in self.snap.revisit_ids() if self.snap.kept_as_weak(c)} if self.a.in_final else set()

    def _reload(self, cid: str | None, evidences: bool = False, structural: bool = False):
        self.snap = rules.load(self.model, self.store, self.aid)
        # regra do requerido leve: avisa no momento em que um P/N passa a T sem correção da empresa
        kept = self._kept_ids()
        for item in sorted(kept - self._kept, key=self.model.order):
            code, initial = self.model.criterion(item).code, self.snap.initial(item).code
            self.toast.show_message(f"{code}: {initial} → T por requerido leve. O problema fica como ponto fraco.", 4200)
        self._kept = kept
        if cid and cid == self.editor.cid:
            ans = self.snap.answer(cid)
            if evidences:
                self.editor.set_evidences(ans.evidences)
            if structural:
                self.editor.render_findings(self.snap)
            else:
                self.editor.update_findings(self.snap)
            self.editor.refresh_requirements(self.snap)
        for c in self.model.criteria:            # apontamentos compartilhados afetam outros itens
            self._refresh_item(c.id)
        self._refresh_progress()
        self._refresh_footer()
        self.saved_lbl.setText("Salvo")
        self.saved_lbl.setToolTip("Salvo automaticamente às " + datetime.now().strftime("%H:%M:%S"))
        self._saved_timer.start()
        self.changed.emit()

    # ================================================================ estado visual
    def _refresh_item(self, cid: str):
        ck = self.snap.check(cid)
        if self.a.in_final:
            r = self.snap.final(cid) if self.snap.revisit(cid) else self.snap.initial(cid)
            if self.snap.revisit(cid) and r is None:
                r = self.snap.initial(cid)       # mostra a nota inicial esmaecida até a nova ser dada
        else:
            r = self.snap.initial(cid)
        self.sidebar.update_item(cid, ck.state.value, r.code if r else None, r.tone if r else None)

    def _refresh_progress(self):
        for p in self.model.processes:
            pr = self.snap.progress(p.criteria)
            self.sidebar.update_process(p.code, pr.done, pr.total)
        total = self.snap.progress()
        noun = "revisitados" if self.a.in_final else "itens completos"
        self.p_text.setText(f"{total.done} de {total.total} {noun}")
        self.p_bar.set_ratio(total.ratio)
        set_variant(self.review_btn, "primary" if total.done == total.total and not self.a.finished else "")

    def _refresh_all(self):
        self.a = self.store.get(self.aid)
        self.snap = rules.load(self.model, self.store, self.aid)
        self.t_title.setText(f"{self.a.organization}  /  {self.a.project}")
        phase = "avaliação final" if self.a.in_final else "avaliação inicial"
        self.t_sub.setText(f"Avaliador(a): {self.a.evaluator}   ·   Nível {self.model.level}   ·   {phase.capitalize()}")
        self.sidebar.set_scope(set(self.snap.revisit_ids()) if self.a.in_final else None)
        for c in self.model.criteria:
            self._refresh_item(c.id)
        self._refresh_progress()
        self._refresh_banner()
        self._update_timer_label()

    def _missing_text(self, cid: str) -> str:
        ck = self.snap.check(cid)
        return "Para avançar, registre: " + ", ".join(ck.missing)

    def _refresh_footer(self):
        cid = self.current()
        if not cid:
            return
        mode = self.mode_for(cid)
        ck = self.snap.check(cid)
        order = self.order
        i = self._index(cid)
        last = i >= len(order) - 1
        self.prev_btn.setEnabled(i > 0)
        self.next_btn.setText("Revisar" if last else "Próximo")
        if mode in (LOCKED, FINAL_LOCKED, FINAL_FIXED):
            self.state_icon.setPixmap(T.icon("lock", T.SECONDARY, 16).pixmap(16, 16))
            self.state_lbl.setText("Sem ajustes: mantém a nota inicial" if mode == FINAL_FIXED else "Somente leitura")
            self.state_lbl.setStyleSheet(f"color: {T.SECONDARY}; background: transparent;")
            self.next_btn.setEnabled(True)
            self.pending_btn.hide()
            return
        if ck.done:
            self.state_icon.setPixmap(T.icon("check-circle", T.GREEN, 18).pixmap(18, 18))
            self.state_lbl.setText("Revisita completa" if mode == FINAL else "Item completo")
            self.state_lbl.setStyleSheet(f"color: {T.TONE_TEXT['ok']}; background: transparent;")
        else:
            incomplete = ck.state is rules.State.INCOMPLETE
            self.state_icon.setPixmap(T.icon("alert-circle", T.ORANGE if incomplete else T.GRAY4, 18).pixmap(18, 18))
            self.state_lbl.setText("Falta " + ", ".join(ck.missing))
            col = T.TONE_TEXT["warn"] if incomplete else T.SECONDARY
            self.state_lbl.setStyleSheet(f"color: {col}; background: transparent;")
        # fail-safe: só avança com o item completo
        self.next_btn.setEnabled(ck.done)
        others = [c for c in self._pending_ids() if c != cid]
        self.pending_btn.setVisible(bool(others))
        n = len(others)
        self.pending_btn.setText(f"{n} {'pendente' if n == 1 else 'pendentes'}")
        self.pending_btn.setToolTip("Ir para o próximo item pendente (Ctrl+Shift+Enter)")
        self.next_btn.setToolTip("Avançar (Ctrl+Enter)" if ck.done else self._missing_text(cid))

    # ================================================================ conclusão
    def _finalize(self):
        if not self.snap.can_finalize():
            self.show_review()
            return
        self.flush()
        self.store.set_status(self.aid, True)
        self._phase_changed()
        self.show_review()
        self.toast.show_message("Avaliação concluída" if self.a.in_final else "Avaliação inicial concluída")
        self.changed.emit()

    def _reopen(self):
        self.flush()
        self.store.set_status(self.aid, False)
        self._phase_changed()
        if self.stack.currentIndex() == 1:
            self.show_review()
        else:
            self.open_item(self.current() or self.order[0], animate=False)
        self.toast.show_message("Avaliação final reaberta" if self.a.in_final else "Avaliação inicial reaberta")
        self.changed.emit()

    def _start_final(self):
        self.flush()
        if not self.snap.revisit_ids():
            self.toast.show_message("Nenhum resultado com apontamento: não há avaliação final a fazer.")
            return
        if not self.a.finished and not self.snap.can_finalize():
            self.show_review()
            return
        self.store.start_final(self.aid)
        self._phase_changed()
        self.open_item(self._first_open_item())
        self.toast.show_message("Avaliação final iniciada")
        self.changed.emit()

    def _back_to_initial(self):
        self.flush()
        self.store.back_to_initial(self.aid)
        self._phase_changed()
        self.open_item(self.current() if self.current() in self.order else self.order[0], animate=False)
        self.toast.show_message("De volta à avaliação inicial. Os registros da avaliação final foram mantidos.")
        self.changed.emit()

    def _phase_changed(self):
        self._persist_time()
        self._refresh_all()
        self._kept = self._kept_ids()
        self._elapsed = self.a.phase_elapsed
        self._update_timer_label()

    def export(self, kind: str):
        self.flush()
        path = export_dialog(self, self.store, self.model, self.aid, kind)
        if path:
            self.toast.show_message(f"Relatório salvo em {path.name}")

    # ================================================================ cronômetro
    def _on_tick(self):
        now = time.monotonic()
        delta = now - self._last_tick
        self._last_tick = now
        if self._paused or self.a.finished:
            return
        if delta > 5:   # sistema suspenso ou travado: não conta
            return
        self._elapsed += 1
        self._unsaved_secs += 1
        self._update_timer_label()
        if self._unsaved_secs >= 15:
            self._persist_time()

    def _persist_time(self):
        if self._unsaved_secs:
            self.store.add_elapsed(self.aid, self._unsaved_secs)
            self._unsaved_secs = 0

    def _update_timer_label(self):
        t = report.fmt_duration(self._elapsed)
        if self.a.finished:
            self.timer_btn.setText(t)
            self.timer_btn.setIcon(T.icon("lock", T.SECONDARY, 15))
            self.timer_btn.setToolTip("Tempo registrado da fase concluída")
            style = f"color: {T.SECONDARY};"
        elif self._paused:
            self.timer_btn.setText(f"{t}  pausado")
            self.timer_btn.setIcon(T.icon("play", T.TONE_TEXT["warn"], 14))
            self.timer_btn.setToolTip("Cronômetro pausado. Clique para retomar (Ctrl+P).")
            style = f"color: {T.TONE_TEXT['warn']}; background: {T.TONE_SOFT['warn']};"
        else:
            self.timer_btn.setText(t)
            self.timer_btn.setIcon(T.icon("clock", T.LABEL_2, 15))
            self.timer_btn.setToolTip(("Tempo da avaliação final" if self.a.in_final else "Tempo da avaliação inicial")
                                      + ". Clique para pausar (Ctrl+P).")
            style = f"color: {T.LABEL};"
        self.timer_btn.setStyleSheet(f"QPushButton {{ {style} border-radius: 15px; padding: 6px 12px; }}")

    def toggle_pause(self):
        if self.a.finished:
            return
        self._paused = not self._paused
        self._persist_time()
        self._update_timer_label()
        self.toast.show_message("Cronômetro pausado" if self._paused else "Cronômetro retomado", 1400)

    def _on_app_state(self, state):
        # pausa automática quando a janela perde o foco por muito tempo é desnecessária;
        # apenas grava o tempo acumulado ao sair da aplicação
        if state != Qt.ApplicationState.ApplicationActive:
            self._persist_time()

    def flush(self):
        self.editor.flush()
        self._persist_time()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.move((self.width() - self.toast.width()) // 2, self.height() - self.toast.height() - 84)
