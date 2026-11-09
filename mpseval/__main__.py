"""Ponto de entrada: python -m mpseval"""
from __future__ import annotations

import sys


def main() -> int:
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtWidgets import QApplication

    from . import errors, windows
    from .core.model import load_model
    from .core.storage import Store
    from .ui import theme
    from .ui.main_window import MainWindow

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    windows.set_process_app_id()     # antes de qualquer janela: agrupa tudo sob o mesmo ícone
    QCoreApplication.setOrganizationName("ITA")
    QCoreApplication.setApplicationName("MPS-Eval")
    app = QApplication(sys.argv)
    errors.install_excepthook()      # erro inesperado vira mensagem + erros.log, em vez de fechar o app
    app.setStyle("Fusion")
    app.setWindowIcon(theme.app_icon())
    theme.load_fonts()
    app.setFont(theme.font(theme.BODY))
    app.setStyleSheet(theme.QSS)

    model = load_model()
    store = Store()
    win = MainWindow(store, model)
    win.show()
    if "--self-test" in sys.argv:
        # usado pelo build: confirma que o executável abre, acha dados, ícone e fontes, e sai
        import tempfile
        from pathlib import Path

        from PyQt6.QtCore import QTimer
        from PyQt6.QtGui import QFontDatabase

        from .core import report, rules
        mem = Store(":memory:")                       # banco descartável: não toca nos dados reais
        a = mem.create("Autoteste", "Autoteste", "Autoteste", model)
        mem.set_rating(a.id, "GPR 1", "P")
        mem.create_finding(a.id, "GPR", ["GPR 1"], "Autoteste")
        snap = rules.load(model, mem, a.id)
        with tempfile.TemporaryDirectory() as tmp:
            pdf = report.export_pdf(Path(tmp) / "t.pdf", model, a, snap)
            xlsx = report.export_xlsx(Path(tmp) / "t.xlsx", model, a, snap)
            files_ok = pdf.read_bytes()[:4] == b"%PDF" and xlsx.read_bytes()[:2] == b"PK"
        mem.close()
        ok = (len(model.criteria) == 27 and model.capability is not None and not theme.app_icon().isNull()
              and "Inter" in QFontDatabase.families() and files_ok)
        QTimer.singleShot(400, lambda: app.exit(0 if ok else 3))
    code = app.exec()
    store.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
