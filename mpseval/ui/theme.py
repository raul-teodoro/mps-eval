"""Tokens visuais no padrão iOS/iPadOS, fontes, ícones e folha de estilo (QSS).

Cores seguem as "system colors" da Apple (modo claro). Para texto colorido sobre
fundo branco são usadas as variantes de alto contraste, que passam no WCAG AA;
as cores vivas ficam para preenchimentos (pontos, barras, switches).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "assets"
APP_ICON = ASSETS / "icon" / "mpseval.ico"
APP_ICON_PNG = ASSETS / "icon" / "mpseval_256.png"

# ---------------------------------------------------------------- superfícies
BG = "#F2F2F7"            # systemGroupedBackground
CARD = "#FFFFFF"          # secondarySystemGroupedBackground
BAR = "#F9F9F9"           # barras de navegação e ferramentas
FILL = "#E3E3E8"          # tertiarySystemFill sobre BG (campo de busca)
FILL_CARD = "#EEEEF0"     # tertiarySystemFill sobre branco (trilho do segmented control)
HOVER = "#E8E8ED"         # realce de linha na barra lateral
HOVER_CARD = "#F6F6F8"    # realce de linha dentro de cartões
PRESSED = "#DCDCE1"

# ---------------------------------------------------------------- texto
LABEL = "#000000"
LABEL_2 = "#3C3C43"       # texto secundário legível (descrições)
SECONDARY = "#8A8A8E"     # secondaryLabel: rótulos, metadados
TERTIARY = "#C4C4C6"      # tertiaryLabel: placeholders, desativado

# ---------------------------------------------------------------- linhas
SEPARATOR = "#C6C6C8"     # separator opaco (hairline)
GRAY4 = "#D1D1D6"
GRAY5 = "#E5E5EA"

# ---------------------------------------------------------------- cores de sistema
BLUE = "#007AFF"
BLUE_HOVER = "#1A88FF"
BLUE_PRESSED = "#0062CC"
BLUE_TINT = "#E5F1FF"
BLUE_TEXT = "#0066D6"     # azul de texto sobre fundo claro (contraste AA)
GREEN = "#34C759"
ORANGE = "#FF9500"
RED = "#FF3B30"
GRAY = "#8E8E93"

# cor por "tom" da escala de caracterização
TONE = {"ok": GREEN, "warn": ORANGE, "bad": RED, "pending": GRAY4, "incomplete": ORANGE}
TONE_TEXT = {"ok": "#248A3D", "warn": "#C93400", "bad": "#D70015", "pending": SECONDARY, "incomplete": "#C93400"}
TONE_SOFT = {"ok": "#E6F7EB", "warn": "#FFF2E0", "bad": "#FFE8E6"}

# aliases usados pelo restante da interface
INK, INK_2, MUTED, FAINT = LABEL, LABEL_2, SECONDARY, TERTIARY
LINE, LINE_2, PAPER, SURFACE, SUNKEN, SELECT = GRAY5, GRAY4, BG, CARD, FILL_CARD, BLUE_TINT

RADIUS_CARD = 12
RADIUS_CONTROL = 10

# ---------------------------------------------------------------- tipografia
# SF Pro é usada quando instalada (macOS); no Windows, Inter (distribuída com o app)
# tem métricas e desenho muito próximos.
_TEXT = ["SF Pro Text", "Inter", "Segoe UI Variable Text", "Segoe UI"]
_DISPLAY = ["SF Pro Display", "Inter Display", "Inter", "Segoe UI Variable Display", "Segoe UI"]

# escala tipográfica (pt), equivalente desktop da escala Dynamic Type do iOS
LARGE_TITLE = 22
TITLE_1 = 18
TITLE_2 = 15
TITLE_3 = 12.5
HEADLINE = 10.5
BODY = 10.5
CALLOUT = 10
SUBHEAD = 9.6
FOOTNOTE = 9
CAPTION = 8.4


def load_fonts() -> None:
    for f in sorted((ASSETS / "fonts").glob("*.otf")):
        QFontDatabase.addApplicationFont(str(f))


def font(size: float = BODY, weight: QFont.Weight = QFont.Weight.Normal, display: bool = False) -> QFont:
    f = QFont()
    f.setFamilies(_DISPLAY if display else _TEXT)
    f.setPointSizeF(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if display and size >= 14:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98.5)   # tracking negativo do SF Display
    return f


# ---------------------------------------------------------------- ícones (traço estilo SF Symbols)
_P = {
    "chevron-left": '<path d="M15 18l-6-6 6-6"/>',
    "chevron-right": '<path d="M9 18l6-6-6-6"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "plus-circle": '<circle cx="12" cy="12" r="9.5" fill="{c}" stroke="none"/><path d="M12 7.5v9M7.5 12h9" stroke="#FFFFFF" stroke-width="2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/>',
    "paperclip": '<path d="M21.4 11.1l-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/>',
    "x": '<path d="M18 6L6 18M6 6l12 12"/>',
    "x-circle": '<circle cx="12" cy="12" r="9.5" fill="{c}" stroke="none"/><path d="M9 9l6 6M15 9l-6 6" stroke="#FFFFFF" stroke-width="2"/>',
    "minus-circle": '<circle cx="12" cy="12" r="9.5" fill="{c}" stroke="none"/><path d="M7.5 12h9" stroke="#FFFFFF" stroke-width="2.2"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    "note": '<path d="M5 6h14M5 12h10M5 18h12"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "pause": '<path d="M9 5v14M15 5v14"/>',
    "play": '<path d="M7 4.5l12 7.5-12 7.5z"/>',
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9.5" fill="{c}" stroke="none"/><path d="M7.5 12.3l3 3 6-6.3" stroke="#FFFFFF" stroke-width="2.2"/>',
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16.2v.3"/>',
    "alert-circle": '<circle cx="12" cy="12" r="9.5" fill="{c}" stroke="none"/><path d="M12 7v6M12 16.6v.2" stroke="#FFFFFF" stroke-width="2.2"/>',
    "download": '<path d="M12 3v12M7 10l5 5 5-5M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "share": '<path d="M12 3v12M7.5 7.5L12 3l4.5 4.5"/><path d="M8 11H6a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-2"/>',
    "more": '<circle cx="12" cy="12" r="9.5"/><circle cx="7.8" cy="12" r=".9" fill="{c}"/><circle cx="12" cy="12" r=".9" fill="{c}"/><circle cx="16.2" cy="12" r=".9" fill="{c}"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "bulb": '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9V16h7v-2.1A6 6 0 0 0 12 3z"/>',
    "flag": '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    "open": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    "unlock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>',
    "keyboard": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10h.01M11 10h.01M15 10h.01M8 14h8"/>',
    "circle": '<circle cx="12" cy="12" r="9.2"/>',
    "link": '<path d="M10 13.5a4.5 4.5 0 0 0 6.4.4l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.6 1.6"/><path d="M14 10.5a4.5 4.5 0 0 0-6.4-.4l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.6-1.6"/>',
    "wrench": '<path d="M14.7 6.3a4 4 0 0 0-5.2 5.2L3.5 17.5l3 3 6-6a4 4 0 0 0 5.2-5.2l-2.4 2.4-2.6-.4-.4-2.6z"/>',
    "doc-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
}


@lru_cache(maxsize=512)
def icon(name: str, color: str = BLUE, size: int = 18, stroke: float = 1.9) -> QIcon:
    body = _P[name].replace("{c}", color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ico = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p, QRectF(0, 0, size * scale, size * scale))
        p.end()
        pm.setDevicePixelRatio(scale)
        ico.addPixmap(pm)
    return ico


def app_icon() -> QIcon:
    ico = QIcon()
    if APP_ICON.exists():
        ico.addFile(str(APP_ICON))
    for s in (16, 32, 64, 128, 256, 512):
        p = ASSETS / "icon" / f"mpseval_{s}.png"
        if p.exists():
            ico.addFile(str(p))
    return ico


def color(c: str, alpha: int | None = None) -> QColor:
    q = QColor(c)
    if alpha is not None:
        q.setAlpha(alpha)
    return q


# ---------------------------------------------------------------- QSS
QSS = f"""
* {{ color: {LABEL}; }}
QMainWindow, #Root {{ background: {BG}; }}
QWidget#Page {{ background: {BG}; }}
QToolTip {{ background: #1C1C1E; color: white; border: none; padding: 5px 8px; border-radius: 6px; }}

/* ---------- botões: padrão = "tinted" (cinza com texto azul) ---------- */
QPushButton {{
    background: {FILL_CARD}; color: {BLUE}; border: 1px solid transparent; border-radius: {RADIUS_CONTROL - 2}px;
    padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {GRAY5}; }}
QPushButton:pressed {{ background: {PRESSED}; }}
QPushButton:focus {{ border: 1px solid {BLUE}; }}
QPushButton:disabled {{ color: {TERTIARY}; background: {FILL_CARD}; }}

QPushButton[variant="primary"] {{ background: {BLUE}; color: white; }}
QPushButton[variant="primary"]:hover {{ background: {BLUE_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background: {BLUE_PRESSED}; }}
QPushButton[variant="primary"]:focus {{ border: 1px solid {BLUE_PRESSED}; }}
QPushButton[variant="primary"]:disabled {{ background: {GRAY5}; color: {TERTIARY}; }}

QPushButton[variant="ghost"] {{ background: transparent; color: {BLUE}; font-weight: 500; }}
QPushButton[variant="ghost"]:hover {{ background: rgba(0, 122, 255, 0.08); }}
QPushButton[variant="ghost"]:pressed {{ background: rgba(0, 122, 255, 0.16); }}
QPushButton[variant="ghost"]:focus {{ border: 1px solid transparent; background: rgba(0, 122, 255, 0.10); }}
QPushButton[variant="ghost"]:disabled {{ color: {TERTIARY}; background: transparent; }}

QPushButton[variant="danger"] {{ background: {RED}; color: white; }}
QPushButton[variant="danger"]:hover {{ background: #FF5147; }}

/* ---------- campos ---------- */
QLineEdit, QPlainTextEdit {{
    background: {CARD}; border: 1px solid {GRAY4}; border-radius: {RADIUS_CONTROL}px;
    padding: 7px 10px; selection-background-color: #B3D7FF; selection-color: {LABEL};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {BLUE}; }}
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{ border: 1px solid {ORANGE}; }}
QLineEdit:read-only, QPlainTextEdit:read-only {{ color: {LABEL_2}; }}

/* busca: preenchida, sem borda */
QLineEdit[role="search"] {{ background: {FILL}; border: 1px solid transparent; border-radius: {RADIUS_CONTROL}px; padding: 6px 8px; }}
QLineEdit[role="search"]:focus {{ background: {CARD}; border: 1px solid {BLUE}; }}

/* campos dentro de cartões: sem borda, como células do iOS */
QLineEdit[role="cell"], QPlainTextEdit[role="cell"] {{ background: transparent; border: 1px solid transparent; border-radius: 0px; padding: 0px; }}
QLineEdit[role="cell"]:focus, QPlainTextEdit[role="cell"]:focus {{ border: 1px solid transparent; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 3px 2px; }}
QScrollBar::handle:vertical {{ background: rgba(0, 0, 0, 0.22); border-radius: 2px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(0, 0, 0, 0.38); }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px 3px; }}
QScrollBar::handle:horizontal {{ background: rgba(0, 0, 0, 0.22); border-radius: 2px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; width: 0; background: none; }}

QListView, QListWidget {{ background: transparent; border: none; outline: none; }}

QMenu {{ background: {CARD}; border: 1px solid {GRAY4}; border-radius: 10px; padding: 5px; }}
QMenu::item {{ padding: 6px 22px 6px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: {BLUE}; color: white; }}
QMenu::separator {{ height: 1px; background: {GRAY5}; margin: 4px 8px; }}
QMenu::icon {{ padding-left: 6px; }}

QDialog {{ background: {BG}; }}
QMessageBox {{ background: {CARD}; }}
QMessageBox QLabel {{ color: {LABEL}; }}

/* ---------- estrutura ---------- */
#NavBar {{ background: {BAR}; border-bottom: 1px solid {SEPARATOR}; }}
#Sidebar {{ background: {BG}; border-right: 1px solid {SEPARATOR}; }}
#Toolbar {{ background: {BAR}; border-top: 1px solid {SEPARATOR}; }}
#Card {{ background: {CARD}; border-radius: {RADIUS_CARD}px; border: 1px solid transparent; }}
#Card[invalid="true"] {{ border: 1px solid {ORANGE}; }}
#Separator {{ background: {GRAY5}; }}
#Pill {{ background: {FILL}; border-radius: 13px; }}
"""
