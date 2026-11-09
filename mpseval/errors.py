"""Registro de erros inesperados.

No PyQt6, uma exceção que escapa de um slot (clique de botão, atalho) encerra o
programa. Este módulo instala um ``sys.excepthook`` que grava o erro em
``erros.log`` (na mesma pasta do banco) e mostra uma mensagem, mantendo o app aberto.
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path


def log_path() -> Path:
    from .core.storage import default_db_path
    return default_db_path().parent / "erros.log"


def log_exception(exc_type, exc, tb, context: str = "") -> Path | None:
    """Acrescenta o erro ao log. Nunca levanta exceção (o log é só um apoio)."""
    try:
        p = log_path()
        with p.open("a", encoding="utf-8") as fh:
            fh.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} {context}\n")
            fh.write("".join(traceback.format_exception(exc_type, exc, tb)))
        return p
    except Exception:       # noqa: BLE001 — falha ao registrar não pode derrubar o app
        return None


def show_error(parent, title: str, message: str, exc: BaseException | None = None, log: Path | None = None):
    from PyQt6.QtWidgets import QMessageBox
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    details = []
    if exc is not None:
        details.append(f"{type(exc).__name__}: {exc}")
    if log is not None:
        details.append(f"Detalhes gravados em:\n{log}")
    if details:
        box.setInformativeText("\n\n".join(details))
    box.exec()


def install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log = log_exception(exc_type, exc, tb, "erro não tratado")
        traceback.print_exception(exc_type, exc, tb)
        try:
            from PyQt6.QtWidgets import QApplication
            if QApplication.instance() is not None:
                show_error(QApplication.activeWindow(), "Erro inesperado",
                           "Ocorreu um erro inesperado. A ação não foi concluída, mas seus dados estão salvos.",
                           exc, log)
        except Exception:   # noqa: BLE001
            pass
    sys.excepthook = hook
