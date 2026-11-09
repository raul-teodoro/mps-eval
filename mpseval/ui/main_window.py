"""Janela principal: alterna entre a lista de avaliações e a área de trabalho."""
from __future__ import annotations

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow, QStackedWidget, QWidget

from .. import windows
from ..core.model import NormModel
from ..core.storage import Store
from . import theme as T
from .export import export_dialog
from .home import HomeView
from .widgets import Toast, fade_in
from .workspace import Workspace


class MainWindow(QMainWindow):
    def __init__(self, store: Store, model: NormModel):
        super().__init__()
        self.store, self.model = store, model
        store.upgrade_data(model)            # bancos da versão 1: CP-G por processo e justificativas
        self.setWindowTitle("MPS-Eval")
        self.setWindowIcon(T.app_icon())
        self.setMinimumSize(1100, 700)
        self._tagged = False
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        self.stack = QStackedWidget(root)
        from PyQt6.QtWidgets import QVBoxLayout
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        self.home = HomeView(store, model)
        self.home.openRequested.connect(self.open_assessment)
        self.home.exportRequested.connect(self._export_from_home)
        self.stack.addWidget(self.home)
        self.workspace: Workspace | None = None
        self.toast = Toast(root)

        s = QShortcut(QKeySequence("Ctrl+N"), self.home)
        s.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        s.activated.connect(self.home.new_assessment)

        geo = QSettings().value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1360, 860)

    def open_assessment(self, aid: int):
        self._close_workspace()
        self.workspace = Workspace(self.store, self.model, aid)
        self.workspace.backRequested.connect(self.show_home)
        self.stack.addWidget(self.workspace)
        self.stack.setCurrentWidget(self.workspace)
        self.setWindowTitle(f"MPS-Eval — {self.workspace.a.organization} / {self.workspace.a.project}")
        fade_in(self.workspace, 170, 0.2)

    def show_home(self):
        self._close_workspace()
        self.home.refresh()
        self.stack.setCurrentWidget(self.home)
        self.setWindowTitle("MPS-Eval")
        fade_in(self.home, 170, 0.2)

    def _close_workspace(self):
        if self.workspace is not None:
            self.workspace.flush()
            self.stack.removeWidget(self.workspace)
            self.workspace.deleteLater()
            self.workspace = None

    def _export_from_home(self, aid: int, kind: str):
        path = export_dialog(self, self.store, self.model, aid, kind)
        if path:
            self.toast.show_message(f"Relatório salvo em {path.name}")

    def showEvent(self, e):
        super().showEvent(e)
        if not self._tagged:        # AUMID + comando de relançamento na janela (barra de tarefas do Windows)
            self._tagged = True
            windows.tag_window(int(self.winId()))

    def closeEvent(self, e):
        if self.workspace is not None:
            self.workspace.flush()
        QSettings().setValue("geometry", self.saveGeometry())
        super().closeEvent(e)
