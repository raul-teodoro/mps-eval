"""Barra lateral estilo iPadOS: navegação não linear com progresso visual por item."""
from __future__ import annotations

from PyQt6.QtCore import QModelIndex, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (QFrame, QLineEdit, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate,
                             QStyleOptionViewItem, QVBoxLayout)

from . import theme as T
from .widgets import paint_status

KIND = Qt.ItemDataRole.UserRole
ID = Qt.ItemDataRole.UserRole + 1
DATA = Qt.ItemDataRole.UserRole + 2


class _Delegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        kind = index.data(KIND)
        return QSize(option.rect.width(), {"process": 62, "group": 30, "item": 36}[kind])

    def paint(self, p: QPainter, opt: QStyleOptionViewItem, index: QModelIndex):
        kind = index.data(KIND)
        d = index.data(DATA) or {}
        r = QRect(opt.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hover = bool(opt.state & QStyle.StateFlag.State_MouseOver)

        if kind == "process":
            top = r.top() + 16
            left = r.left() + 18
            p.setPen(QColor(T.LABEL))
            p.setFont(T.font(T.TITLE_3, QFont.Weight.Bold, display=True))
            code_w = QFontMetrics(p.font()).horizontalAdvance(d["code"])
            p.drawText(QRect(left, top, code_w + 4, 20), Qt.AlignmentFlag.AlignVCenter, d["code"])
            p.setPen(QColor(T.SECONDARY))
            fnt = T.font(T.SUBHEAD)
            p.setFont(fnt)
            avail = r.width() - code_w - 100
            p.drawText(QRect(left + code_w + 8, top, avail, 20), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(fnt).elidedText(d["name"], Qt.TextElideMode.ElideRight, avail))
            complete = d["done"] == d["total"]
            p.setFont(T.font(T.FOOTNOTE, QFont.Weight.DemiBold))
            p.setPen(QColor(T.TONE_TEXT["ok"] if complete else T.SECONDARY))
            p.drawText(QRect(r.right() - 72, top, 54, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{d['done']} de {d['total']}")
            bar = QRectF(left, top + 28, r.width() - 36, 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T.GRAY5))
            p.drawRoundedRect(bar, 2, 2)
            ratio = d["done"] / d["total"] if d["total"] else 0
            if ratio:
                p.setBrush(QColor(T.GREEN if complete else T.BLUE))
                p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(4, bar.width() * ratio), 4), 2, 2)

        elif kind == "group":
            p.setPen(QColor(T.SECONDARY))
            p.setFont(T.font(T.FOOTNOTE, QFont.Weight.Medium))
            p.drawText(QRect(r.left() + 18, r.top(), r.width() - 36, r.height() - 5),
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft, d["name"])

        else:
            cell = QRectF(r).adjusted(10, 1, -10, -1)
            if selected:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(T.BLUE))
                p.drawRoundedRect(cell, 9, 9)
            elif hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(T.HOVER))
                p.drawRoundedRect(cell, 9, 9)
            paint_status(p, QPointF(cell.left() + 17, cell.center().y()), d["state"], d.get("tone"),
                         on_accent=selected)
            fg = QColor("#FFFFFF") if selected else QColor(T.LABEL)
            p.setPen(fg)
            p.setFont(T.font(T.SUBHEAD, QFont.Weight.DemiBold))
            p.drawText(QRectF(cell.left() + 32, cell.top(), 58, cell.height()), Qt.AlignmentFlag.AlignVCenter,
                       d["code"])
            fnt = T.font(T.SUBHEAD)
            p.setFont(fnt)
            p.setPen(fg if selected else QColor(T.LABEL_2))
            avail = int(cell.width() - 32 - 60 - 26)
            p.drawText(QRectF(cell.left() + 92, cell.top(), avail, cell.height()), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(fnt).elidedText(d["title"], Qt.TextElideMode.ElideRight, avail))
            if d.get("rating"):
                p.setFont(T.font(T.FOOTNOTE, QFont.Weight.Bold))
                if selected:
                    p.setPen(QColor("#FFFFFF"))
                else:
                    p.setPen(QColor(T.TONE_TEXT[d["tone"]]) if d["state"] == "completo" else QColor(T.TERTIARY))
                p.drawText(QRectF(cell.right() - 26, cell.top(), 16, cell.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, d["rating"])
        p.restore()


class Sidebar(QFrame):
    itemSelected = pyqtSignal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(340)
        self.model = model
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 8)
        lay.setSpacing(4)

        self.search = QLineEdit()
        self.search.setProperty("role", "search")
        self.search.setPlaceholderText("Buscar critério")
        self.search.setToolTip("Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(34)
        self.search.addAction(T.icon("search", T.SECONDARY, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._open_first)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(14, 0, 14, 2)
        wrap.addWidget(self.search)
        lay.addLayout(wrap)

        self.list = QListWidget()
        self.list.setItemDelegate(_Delegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setUniformItemSizes(False)
        self.list.currentItemChanged.connect(self._changed)
        lay.addWidget(self.list, 1)

        self._scope: set[str] | None = None
        self._rows: dict[str, QListWidgetItem] = {}
        self._proc_rows: dict[str, QListWidgetItem] = {}
        self._group_rows: list[tuple[QListWidgetItem, list[str], str]] = []
        for proc in model.processes:
            it = QListWidgetItem()
            it.setData(KIND, "process")
            it.setData(DATA, {"code": proc.code, "name": proc.name, "done": 0, "total": len(proc.criteria)})
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.list.addItem(it)
            self._proc_rows[proc.code] = it
            for gname, items in proc.groups:
                g = QListWidgetItem()
                g.setData(KIND, "group")
                g.setData(DATA, {"name": gname})
                g.setFlags(Qt.ItemFlag.NoItemFlags)
                self.list.addItem(g)
                self._group_rows.append((g, [c.id for c in items], proc.code))
                for c in items:
                    row = QListWidgetItem()
                    row.setData(KIND, "item")
                    row.setData(ID, c.id)
                    row.setData(DATA, {"code": c.code, "title": c.title, "state": "pendente"})
                    row.setToolTip(f"{c.code} — {c.title}")
                    self.list.addItem(row)
                    self._rows[c.id] = row

    # ------------------------------------------------------------
    def _changed(self, cur: QListWidgetItem | None, _prev):
        if cur is not None and cur.data(KIND) == "item":
            self.itemSelected.emit(cur.data(ID))

    def select(self, cid: str):
        row = self._rows[cid]
        if self.list.currentItem() is not row:
            self.list.blockSignals(True)
            self.list.setCurrentItem(row)
            self.list.blockSignals(False)
        self.list.scrollToItem(row, QListWidget.ScrollHint.EnsureVisible)

    def update_item(self, cid: str, state: str, rating: str | None, tone: str | None):
        row = self._rows[cid]
        d = dict(row.data(DATA))
        d.update(state=state, rating=rating, tone=tone)
        row.setData(DATA, d)

    def update_process(self, code: str, done: int, total: int):
        row = self._proc_rows[code]
        d = dict(row.data(DATA))
        d.update(done=done, total=total)
        row.setData(DATA, d)

    def set_scope(self, ids: set[str] | None):
        """Restringe a lista aos itens da fase (na avaliação final, só os que têm apontamento)."""
        self._scope = ids
        self.search.setPlaceholderText("Buscar entre os resultados com apontamento" if ids is not None
                                       else "Buscar critério")
        self._filter(self.search.text())

    def _filter(self, text: str):
        q = text.strip().lower()
        visible_by_proc: dict[str, int] = {}
        for c in self.model.criteria:
            hit = not q or q in c.code.lower() or q in c.title.lower() or q in c.text.lower() \
                or q.replace(" ", "") in c.id.lower().replace(" ", "")
            hit = hit and (self._scope is None or c.id in self._scope)
            self._rows[c.id].setHidden(not hit)
            visible_by_proc[c.process] = visible_by_proc.get(c.process, 0) + int(hit)
        for g, ids, _proc in self._group_rows:
            g.setHidden(all(self._rows[i].isHidden() for i in ids))
        for code, row in self._proc_rows.items():
            row.setHidden(visible_by_proc.get(code, 0) == 0)

    def _open_first(self):
        cid = self.first_visible()
        if cid:
            self.list.setCurrentItem(self._rows[cid])
            self.list.setFocus()

    def first_visible(self) -> str | None:
        for cid, row in self._rows.items():
            if not row.isHidden():
                return cid
        return None
