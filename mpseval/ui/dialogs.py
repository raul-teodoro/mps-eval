"""Diálogos auxiliares."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QFrame, QGridLayout, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from . import theme as T
from .widgets import Card, SectionHeader, button, label, separator

SHORTCUTS = [
    ("Caracterizar", [("1  2  3  4", "T, L, P ou N (fora de campos de texto)"),
                      ("5", "NA, só na nova caracterização da avaliação final"),
                      ("Alt + 1…5", "o mesmo, em qualquer lugar"),
                      ("← →", "trocar a opção do controle em foco")]),
    ("Navegar", [("Ctrl + Enter", "próximo item (exige o item completo)"),
                 ("Ctrl + Shift + Enter", "próximo item pendente"),
                 ("Ctrl + ↑ / ↓", "item anterior / seguinte, livremente"),
                 ("Ctrl + F", "buscar critério; Enter abre o primeiro resultado"),
                 ("Ctrl + R", "revisão final"),
                 ("Esc", "fechar a revisão ou voltar à lista")]),
    ("Registrar", [("Ctrl + E", "ir para o campo de evidência"),
                   ("Enter", "adicionar a evidência digitada"),
                   ("Ctrl + Z", "desfazer a última remoção de evidência"),
                   ("Ctrl + P", "pausar ou retomar o cronômetro")]),
]


class ShortcutsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atalhos de teclado")
        self.setMinimumSize(540, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("NavBar")
        bar.setFixedHeight(54)
        bl = QGridLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        bl.addWidget(label("Atalhos de teclado", T.HEADLINE + 0.5, QFont.Weight.DemiBold), 0, 1,
                     Qt.AlignmentFlag.AlignCenter)
        ok = button("OK", "ghost")
        ok.setFont(T.font(T.BODY, QFont.Weight.DemiBold))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bl.addWidget(ok, 0, 2, Qt.AlignmentFlag.AlignRight)
        bl.setColumnStretch(0, 1)
        bl.setColumnStretch(2, 1)
        lay.addWidget(bar)

        content = QWidget()
        content.setObjectName("Page")
        body = QVBoxLayout(content)
        body.setContentsMargins(20, 18, 20, 24)
        body.setSpacing(0)
        for gi, (title, rows) in enumerate(SHORTCUTS):
            if gi:
                body.addSpacing(20)
            body.addWidget(SectionHeader(title))
            body.addSpacing(6)
            card = Card()
            for i, (keys, desc) in enumerate(rows):
                if i:
                    card.lay.addWidget(separator(16))
                r = QWidget()
                rl = QHBoxLayout(r)
                rl.setContentsMargins(16, 9, 16, 9)
                rl.setSpacing(14)
                k = label(keys, T.FOOTNOTE, QFont.Weight.DemiBold)
                k.setStyleSheet(f"color: {T.LABEL}; background: {T.FILL_CARD}; border-radius: 6px; padding: 3px 8px;")
                k.setFixedWidth(158)
                k.setAlignment(Qt.AlignmentFlag.AlignCenter)
                rl.addWidget(k)
                rl.addWidget(label(desc, T.BODY, color=T.LABEL_2, wrap=True), 1)
                card.lay.addWidget(r)
            body.addWidget(card)
        body.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(content)
        lay.addWidget(sc, 1)
