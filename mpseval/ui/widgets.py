"""Componentes visuais no padrão iOS, desenhados à mão para ficarem leves e fluidos."""
from __future__ import annotations

from PyQt6.QtCore import (QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
                             QSizePolicy, QToolButton, QToolTip, QVBoxLayout, QWidget)

from . import theme as T

EASE = QEasingCurve.Type.OutCubic
SPRING = QEasingCurve.Type.OutBack


def fade_in(w: QWidget, ms: int = 150, start: float = 0.0) -> None:
    """Entrada suave; remove o efeito ao final para não pesar a renderização."""
    eff = QGraphicsOpacityEffect(w)
    eff.setOpacity(start)
    w.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", w)
    anim.setDuration(ms)
    anim.setStartValue(start)
    anim.setEndValue(1.0)
    anim.setEasingCurve(EASE)
    anim.finished.connect(lambda: w.setGraphicsEffect(None))
    anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)


def label(text: str = "", size: float = T.BODY, weight=QFont.Weight.Normal, color: str = T.LABEL,
          wrap: bool = False, display: bool = False, selectable: bool = False) -> QLabel:
    lb = QLabel(text)
    lb.setFont(T.font(size, weight, display))
    lb.setStyleSheet(f"color: {color}; background: transparent;")
    lb.setWordWrap(wrap)
    if selectable:
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lb


def button(text: str, variant: str = "", icon: str | None = None, icon_color: str | None = None,
           tooltip: str = "") -> QPushButton:
    """variant: "" (tinted), "primary" (preenchido), "ghost" (só texto azul) ou "danger"."""
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if icon:
        col = icon_color or ("#FFFFFF" if variant in ("primary", "danger") else T.BLUE)
        b.setIcon(T.icon(icon, col, 16))
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFont(T.font(T.CALLOUT, QFont.Weight.DemiBold if variant != "ghost" else QFont.Weight.Medium))
    if tooltip:
        b.setToolTip(tooltip)
    return b


def set_variant(b: QPushButton, variant: str) -> None:
    b.setProperty("variant", variant)
    b.style().unpolish(b)
    b.style().polish(b)


def icon_button(name: str, tooltip: str, color: str = T.BLUE, size: int = 18) -> QToolButton:
    b = QToolButton()
    b.setIcon(T.icon(name, color, size))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setStyleSheet("QToolButton { border: none; border-radius: 8px; padding: 5px; background: transparent; }"
                    "QToolButton:hover { background: rgba(0, 122, 255, 0.08); }"
                    "QToolButton:pressed { background: rgba(0, 122, 255, 0.16); }")
    return b


def clear_layout(layout) -> None:
    """Remove e descarta imediatamente todos os itens (sem "fantasmas" até o deleteLater)."""
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif it.layout() is not None:
            clear_layout(it.layout())


def separator(inset: int = 0) -> QWidget:
    """Hairline com recuo à esquerda, como entre células do iOS."""
    holder = QWidget()
    holder.setFixedHeight(1)
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(inset, 0, 0, 0)
    line = QFrame()
    line.setObjectName("Separator")
    line.setFixedHeight(1)
    lay.addWidget(line)
    return holder


hline = separator


# ------------------------------------------------------------ listas agrupadas
class Card(QFrame):
    """Cartão branco de cantos arredondados (lista "inset grouped")."""

    def __init__(self, padding: tuple[int, int, int, int] = (0, 0, 0, 0), spacing: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*padding)
        self.lay.setSpacing(spacing)

    def set_invalid(self, on: bool) -> None:
        self.setProperty("invalid", on)
        self.style().unpolish(self)
        self.style().polish(self)


class SectionHeader(QWidget):
    """Cabeçalho de seção: título em cinza secundário e, opcionalmente, um texto à direita."""

    def __init__(self, title: str, aside: str = "", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)
        self.title = label(title, T.FOOTNOTE, QFont.Weight.Medium, T.SECONDARY)
        lay.addWidget(self.title)
        lay.addStretch(1)
        self.aside = label(aside, T.FOOTNOTE, color=T.SECONDARY)
        lay.addWidget(self.aside)

    def set_aside(self, text: str, color: str = T.SECONDARY) -> None:
        self.aside.setText(text)
        self.aside.setStyleSheet(f"color: {color}; background: transparent;")


def section_footer(text: str) -> QLabel:
    lb = label(text, T.CAPTION, color=T.SECONDARY, wrap=True)
    lb.setContentsMargins(16, 0, 16, 0)
    return lb


class Row(QFrame):
    """Célula clicável dentro de um Card, com realce ao passar o mouse e chevron opcional."""
    clicked = pyqtSignal()

    def __init__(self, chevron: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("Row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(16, 10, 12, 10)
        self.lay.setSpacing(12)
        self._chevron = chevron
        self._pos = "middle"
        self._apply_style()

    def finish(self) -> None:
        if self._chevron:
            ch = QLabel()
            ch.setPixmap(T.icon("chevron-right", T.TERTIARY, 14, 2.4).pixmap(14, 14))
            ch.setStyleSheet("background: transparent;")
            self.lay.addWidget(ch)
        for i in range(self.lay.count()):
            w = self.lay.itemAt(i).widget()
            if w is not None and not isinstance(w, QAbstractButton):
                w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_position(self, pos: str) -> None:
        """first | middle | last | only: arredonda os cantos certos do realce."""
        self._pos = pos
        self._apply_style()

    def _apply_style(self):
        r = T.RADIUS_CARD
        tl = tr = r if self._pos in ("first", "only") else 0
        bl = br = r if self._pos in ("last", "only") else 0
        rad = (f"border-top-left-radius: {tl}px; border-top-right-radius: {tr}px;"
               f" border-bottom-left-radius: {bl}px; border-bottom-right-radius: {br}px;")
        self.setStyleSheet(f"#Row {{ background: transparent; {rad} }}"
                           f"#Row:hover {{ background: {T.HOVER_CARD}; {rad} }}")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


def grouped_rows(card: Card, rows: list[QWidget], inset: int = 16) -> None:
    """Adiciona linhas ao cartão com separadores recuados e cantos corretos."""
    for i, r in enumerate(rows):
        if isinstance(r, Row):
            r.set_position("only" if len(rows) == 1 else "first" if i == 0 else "last" if i == len(rows) - 1 else "middle")
        if i:
            card.lay.addWidget(separator(inset))
        card.lay.addWidget(r)


# ------------------------------------------------------------ progresso
class ProgressBar(QWidget):
    """Barra fina (UIProgressView) com transição animada."""

    def __init__(self, height: int = 4, parent=None):
        super().__init__(parent)
        self._v = 0.0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim = QVariantAnimation(self, duration=300, easingCurve=EASE)
        self._anim.valueChanged.connect(self._set)

    def _set(self, v):
        self._v = float(v)
        self.update()

    def set_ratio(self, r: float, animate: bool = True):
        r = max(0.0, min(1.0, r))
        self._anim.stop()
        if not animate:
            self._set(r)
            return
        self._anim.setStartValue(self._v)
        self._anim.setEndValue(r)
        self._anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        rad = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.GRAY5))
        p.drawRoundedRect(r, rad, rad)
        if self._v > 0:
            w = max(r.height(), r.width() * self._v)
            p.setBrush(QColor(T.GREEN if self._v >= 0.999 else T.BLUE))
            p.drawRoundedRect(QRectF(0, 0, w, r.height()), rad, rad)


class ProgressRing(QWidget):
    def __init__(self, size: int = 40, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.ratio = 0.0
        self.text = ""

    def set(self, ratio: float, text: str):
        self.ratio, self.text = ratio, text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self.width()
        pen_w = max(3.0, s / 10)
        rect = QRectF(pen_w / 2 + 1, pen_w / 2 + 1, s - pen_w - 2, s - pen_w - 2)
        pen = QPen(QColor(T.GRAY5), pen_w)
        p.setPen(pen)
        p.drawEllipse(rect)
        done = self.ratio >= 0.999
        if self.ratio > 0:
            pen.setColor(QColor(T.GREEN if done else T.BLUE))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, -int(360 * 16 * self.ratio))
        if done:
            p.setPen(QPen(QColor(T.GREEN), max(2.0, s / 16), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            c = s / 2
            k = s / 40
            path = QPainterPath(QPointF(c - 6 * k, c + 0.5 * k))
            path.lineTo(c - 1.5 * k, c + 5 * k)
            path.lineTo(c + 7 * k, c - 4.5 * k)
            p.drawPath(path)
        else:
            p.setPen(QColor(T.LABEL))
            p.setFont(T.font(s / 5.6, QFont.Weight.DemiBold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)


class DistributionBar(QWidget):
    """Barra segmentada com a distribuição de caracterizações de um processo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self.segments: list[tuple[int, str]] = []

    def set_segments(self, segments: list[tuple[int, str]]):
        self.segments = segments
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(n for n, _ in self.segments) or 1
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 4, 4)
        p.setClipPath(clip)
        x = 0.0
        for n, col in self.segments:
            if not n:
                continue
            w = r.width() * n / total
            p.fillRect(QRectF(x, 0, w + 0.5, r.height()), QColor(col))
            x += w
            p.fillRect(QRectF(x - 1, 0, 2, r.height()), QColor(T.CARD))


# ------------------------------------------------------------ status
def paint_status(p: QPainter, center: QPointF, state: str, tone: str | None, radius: float = 5.5,
                 on_accent: bool = False) -> None:
    """Estado de um item: anel cinza (pendente), anel laranja com ponto (incompleto) ou
    disco na cor da caracterização (completo). on_accent: desenhado sobre a seleção azul."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if on_accent:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(center, radius + 1.6, radius + 1.6)
    if state == "completo":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.TONE[tone or "ok"]))
        p.drawEllipse(center, radius, radius)
    elif state == "incompleto":
        p.setPen(QPen(QColor(T.ORANGE), 1.7))
        p.setBrush(QColor(T.CARD))
        p.drawEllipse(center, radius - 0.6, radius - 0.6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.ORANGE))
        p.drawEllipse(center, 2.1, 2.1)
    else:
        p.setPen(QPen(QColor(T.GRAY4 if not on_accent else T.GRAY), 1.7))
        p.setBrush(Qt.BrushStyle.NoBrush if not on_accent else QColor("#FFFFFF"))
        p.drawEllipse(center, radius - 0.6, radius - 0.6)
    p.restore()


# ------------------------------------------------------------ segmented control
class SegmentedRating(QWidget):
    """UISegmentedControl ampliado para a escala T/L/P/N.

    O "polegar" branco desliza até o segmento escolhido; a letra mantém a cor do
    seu tom (verde, laranja, vermelho) para reconhecimento imediato.
    """
    ratingChanged = pyqtSignal(object)   # str | None

    def __init__(self, scale, parent=None):
        super().__init__(parent)
        self.scale = list(scale)
        self.codes = [r.code for r in self.scale]
        self._value: str | None = None
        self._thumb_x = -1.0          # posição animada (índice fracionário); -1 = sem seleção
        self._thumb_alpha = 0.0
        self._hover = -1
        self._press = -1
        self.setMinimumHeight(66)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Caracterização")
        self._anim = QVariantAnimation(self, duration=260, easingCurve=EASE)
        self._anim.valueChanged.connect(self._on_anim)
        self._fade = QVariantAnimation(self, duration=160, easingCurve=EASE)
        self._fade.valueChanged.connect(self._on_fade)

    # ---------- API compatível com a barra anterior
    def value(self) -> str | None:
        return self._value

    def set_value(self, code: str | None):
        """Define sem animação e sem emitir sinal (ao abrir um item)."""
        self._anim.stop()
        self._fade.stop()
        self._value = code
        if code in self.codes:
            self._thumb_x = float(self.codes.index(code))
            self._thumb_alpha = 1.0
        else:
            self._thumb_alpha = 0.0
        self.update()

    def select(self, code: str):
        """Seleção por teclado ou clique: anima e emite."""
        if not self.isEnabled() or code not in self.codes or code == self._value:
            return
        self._move_to(code)
        self.ratingChanged.emit(code)

    def clear(self):
        if self._value is None or not self.isEnabled():
            return
        self._value = None
        self._fade.stop()
        self._fade.setStartValue(self._thumb_alpha)
        self._fade.setEndValue(0.0)
        self._fade.start()
        self.ratingChanged.emit(None)

    # ---------- animação
    def _move_to(self, code: str):
        idx = float(self.codes.index(code))
        self._value = code
        if self._thumb_alpha < 0.05:          # surge no lugar
            self._thumb_x = idx
            self._fade.stop()
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.start()
        else:                                  # desliza
            self._anim.stop()
            self._anim.setStartValue(self._thumb_x)
            self._anim.setEndValue(idx)
            self._anim.start()

    def _on_anim(self, v):
        self._thumb_x = float(v)
        self.update()

    def _on_fade(self, v):
        self._thumb_alpha = float(v)
        self.update()

    # ---------- geometria
    def _track(self) -> QRectF:
        return QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

    def _seg_w(self) -> float:
        return (self._track().width() - 4) / len(self.codes)

    def _index_at(self, x: float) -> int:
        i = int((x - 2) // self._seg_w())
        return max(0, min(len(self.codes) - 1, i))

    # ---------- eventos
    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().x())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self._press = -1
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._press = self._index_at(e.position().x())
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._press >= 0:
            i = self._index_at(e.position().x())
            if i == self._press and self.rect().contains(e.position().toPoint()):
                self.select(self.codes[i])
            self._press = -1
            self.update()

    def keyPressEvent(self, e):
        k = e.key()
        cur = self.codes.index(self._value) if self._value in self.codes else -1
        if k in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.select(self.codes[min(len(self.codes) - 1, cur + 1)])
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.select(self.codes[max(0, cur - 1 if cur >= 0 else 0)])
        elif k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.clear()
        else:
            super().keyPressEvent(e)

    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            i = self._index_at(e.pos().x())
            r = self.scale[i]
            QToolTip.showText(e.globalPos(), f"{r.label}  (tecla {i + 1})", self)
            return True
        return super().event(e)

    def focusInEvent(self, e):
        self.update()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.update()
        super().focusOutEvent(e)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.EnabledChange:
            self.setCursor(Qt.CursorShape.PointingHandCursor if self.isEnabled() else Qt.CursorShape.ArrowCursor)
        super().changeEvent(e)

    def sizeHint(self):
        return QSize(560, 66)

    # ---------- desenho
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tr = self._track()
        enabled = self.isEnabled()
        # trilho
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.FILL_CARD))
        p.drawRoundedRect(tr, 10, 10)
        sw = self._seg_w()
        n = len(self.codes)
        sel = self.codes.index(self._value) if self._value in self.codes else -1

        # realce de hover/pressão
        for i, a in ((self._hover, 10), (self._press, 22)):
            if 0 <= i != sel and enabled:
                r = QRectF(tr.left() + 2 + i * sw, tr.top() + 2, sw, tr.height() - 4).adjusted(1, 1, -1, -1)
                p.setBrush(QColor(0, 0, 0, a))
                p.drawRoundedRect(r, 8, 8)

        # separadores entre segmentos (somem junto ao polegar)
        p.setPen(QPen(QColor(T.GRAY4), 1))
        for i in range(1, n):
            near = self._thumb_alpha > 0.5 and abs(self._thumb_x + 0.5 - i) < 0.75
            if not near:
                x = tr.left() + 2 + i * sw
                p.drawLine(QPointF(x, tr.top() + 16), QPointF(x, tr.bottom() - 16))

        # polegar com sombra suave
        if self._thumb_alpha > 0.01:
            th = QRectF(tr.left() + 2 + self._thumb_x * sw, tr.top() + 2, sw, tr.height() - 4)
            alpha = self._thumb_alpha * (1.0 if enabled else 0.7)
            p.setPen(Qt.PenStyle.NoPen)
            for dy, a in ((3, 10), (1.5, 14), (0.5, 18)):
                p.setBrush(QColor(0, 0, 0, int(a * alpha)))
                p.drawRoundedRect(th.adjusted(0, dy, 0, dy), 8, 8)
            p.setBrush(QColor(255, 255, 255, int(255 * alpha)))
            p.setPen(QPen(QColor(0, 0, 0, int(10 * alpha)), 0.5))
            p.drawRoundedRect(th, 8, 8)

        # rótulos
        for i, r in enumerate(self.scale):
            seg = QRectF(tr.left() + 2 + i * sw, tr.top(), sw, tr.height())
            selected = i == sel
            letter = QColor(T.TONE_TEXT[r.tone])
            if not enabled and not selected:
                letter.setAlpha(110)
            p.setPen(letter)
            p.setFont(T.font(17, QFont.Weight.Bold, display=True))
            p.drawText(seg.adjusted(0, 9, 0, -26), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, r.code)
            p.setPen(QColor(T.LABEL if selected else T.SECONDARY) if enabled or selected else QColor(T.TERTIARY))
            p.setFont(T.font(T.CAPTION + 0.4, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
            p.drawText(seg.adjusted(4, 0, -4, -11), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                       r.short)
            p.setPen(QColor(T.TERTIARY))
            p.setFont(T.font(T.CAPTION - 0.6, QFont.Weight.Medium))
            p.drawText(seg.adjusted(0, 7, -10, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, str(i + 1))

        # anel de foco (teclado)
        if self.hasFocus():
            p.setPen(QPen(QColor(0, 122, 255, 150), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(tr.adjusted(1, 1, -1, -1), 10, 10)


RatingBar = SegmentedRating


class Option:
    """Opção de um controle segmentado de texto."""

    def __init__(self, code: str, label: str, tone: str = "neutral"):
        self.code, self.label, self.short, self.tone = code, label, label, tone


class Segmented(SegmentedRating):
    """Controle segmentado compacto, só texto (ex.: Sim | Não | Sem correção)."""

    def __init__(self, options: list[Option], parent=None, min_seg: int = 72):
        super().__init__(options, parent)
        self._min_seg = min_seg
        self.setMinimumHeight(32)
        self.setMaximumHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Opções")

    def sizeHint(self):
        fm = QFontMetrics(T.font(T.SUBHEAD, QFont.Weight.DemiBold))
        w = max(self._min_seg, max(fm.horizontalAdvance(o.label) for o in self.scale) + 28)
        return QSize(int(w * len(self.scale) + 4), 32)

    def minimumSizeHint(self):
        return self.sizeHint()

    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            return True
        return QWidget.event(self, e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tr = self._track()
        enabled = self.isEnabled()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.FILL_CARD))
        p.drawRoundedRect(tr, 8, 8)
        sw = self._seg_w()
        n = len(self.codes)
        sel = self.codes.index(self._value) if self._value in self.codes else -1
        for i, a in ((self._hover, 10), (self._press, 22)):
            if 0 <= i != sel and enabled:
                r = QRectF(tr.left() + 2 + i * sw, tr.top() + 2, sw, tr.height() - 4).adjusted(1, 1, -1, -1)
                p.setBrush(QColor(0, 0, 0, a))
                p.drawRoundedRect(r, 6, 6)
        p.setPen(QPen(QColor(T.GRAY4), 1))
        for i in range(1, n):
            near = self._thumb_alpha > 0.5 and abs(self._thumb_x + 0.5 - i) < 0.75
            if not near:
                x = tr.left() + 2 + i * sw
                p.drawLine(QPointF(x, tr.top() + 8), QPointF(x, tr.bottom() - 8))
        if self._thumb_alpha > 0.01:
            th = QRectF(tr.left() + 2 + self._thumb_x * sw, tr.top() + 2, sw, tr.height() - 4)
            alpha = self._thumb_alpha * (1.0 if enabled else 0.7)
            p.setPen(Qt.PenStyle.NoPen)
            for dy, a in ((2, 10), (1, 14)):
                p.setBrush(QColor(0, 0, 0, int(a * alpha)))
                p.drawRoundedRect(th.adjusted(0, dy, 0, dy), 6, 6)
            p.setBrush(QColor(255, 255, 255, int(255 * alpha)))
            p.setPen(QPen(QColor(0, 0, 0, int(10 * alpha)), 0.5))
            p.drawRoundedRect(th, 6, 6)
        for i, o in enumerate(self.scale):
            seg = QRectF(tr.left() + 2 + i * sw, tr.top(), sw, tr.height())
            selected = i == sel
            col = T.TONE_TEXT.get(o.tone, T.LABEL) if selected else (T.LABEL_2 if enabled else T.TERTIARY)
            p.setPen(QColor(col))
            p.setFont(T.font(T.SUBHEAD, QFont.Weight.DemiBold if selected else QFont.Weight.Normal))
            p.drawText(seg, Qt.AlignmentFlag.AlignCenter, o.label)
        if self.hasFocus():
            p.setPen(QPen(QColor(0, 122, 255, 150), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(tr.adjusted(1, 1, -1, -1), 8, 8)


class SelectRow(Row):
    """Linha com marcação múltipla no estilo iOS (círculo vazio ou com check azul)."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False, enabled: bool = True, parent=None):
        super().__init__(chevron=False, parent=parent)
        self._checked = checked
        self._enabled = enabled
        self.mark = QLabel()
        self.mark.setStyleSheet("background: transparent;")
        self.lay.addWidget(self.mark)
        self._paint_mark()
        if not enabled:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.clicked.connect(self._flip)

    def _paint_mark(self):
        if self._checked:
            pm = T.icon("check-circle", T.BLUE if self._enabled else T.GRAY4, 22).pixmap(22, 22)
        else:
            pm = T.icon("circle", T.GRAY4 if self._enabled else T.GRAY5, 22, 1.6).pixmap(22, 22)
        self.mark.setPixmap(pm)

    def _flip(self):
        if self._enabled:
            self.set_checked(not self._checked)
            self.toggled.emit(self._checked)

    def set_checked(self, on: bool):
        self._checked = on
        self._paint_mark()

    def is_checked(self) -> bool:
        return self._checked


# ------------------------------------------------------------ switch
class Switch(QAbstractButton):
    """UISwitch: trilho verde quando ligado, botão branco que desliza."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 24)
        self._pos = 0.0
        self._anim = QVariantAnimation(self, duration=220, easingCurve=EASE)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def _on_anim(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on: bool):
        super().setChecked(on)
        if not self._anim.state() == QVariantAnimation.State.Running:
            self._pos = 1.0 if on else 0.0
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        off, on = QColor("#E9E9EA"), QColor(T.GREEN)
        t = self._pos
        track = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.left() + 2 + (r.width() - d - 4) * t
        knob = QRectF(x, r.top() + 2, d, d)
        for dy, a in ((1.5, 18), (0.5, 26)):
            p.setBrush(QColor(0, 0, 0, a))
            p.drawEllipse(knob.adjusted(0, dy, 0, dy))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(knob)
        if self.hasFocus():
            p.setPen(QPen(QColor(0, 122, 255, 150), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)

    def sizeHint(self):
        return QSize(40, 24)


# ------------------------------------------------------------ chip / pílula
def chip(text: str, fg: str, bg: str) -> QLabel:
    c = label(text, T.CAPTION + 0.4, QFont.Weight.DemiBold, fg)
    c.setStyleSheet(f"color: {fg}; background: {bg}; border-radius: 11px; padding: 0px 10px;")
    c.setAlignment(Qt.AlignmentFlag.AlignCenter)
    c.setFixedHeight(22)
    c.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return c


# ------------------------------------------------------------ HUD (toast)
class Toast(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFont(T.font(T.CALLOUT, QFont.Weight.Medium))
        self.setStyleSheet("background: rgba(30, 30, 32, 0.92); color: white; border-radius: 14px; padding: 10px 18px;")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._eff)
        self._anim = QPropertyAnimation(self._eff, b"opacity", self)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self._out)

    def show_message(self, text: str, ms: int = 2400):
        self.setText(text)
        self.adjustSize()
        par = self.parentWidget()
        self.move((par.width() - self.width()) // 2, par.height() - self.height() - 84)
        self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setDuration(140)
        self._anim.setStartValue(self._eff.opacity() if self.isVisible() else 0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(ms)

    def _out(self):
        self._anim.stop()
        self._anim.setDuration(260)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()
