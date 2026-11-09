"""Integração com a barra de tarefas do Windows.

O Windows agrupa janelas e atalhos fixados pelo *AppUserModelID* (AUMID).
Sem ele, o app aparece como "python.exe" e fixar a janela fixa o Python, não o
MPS-Eval. Para que tudo vire um único ícone, o mesmo AUMID precisa estar em:

1. o processo (``set_process_app_id``), chamado antes de criar qualquer janela;
2. o atalho ``.lnk`` (``criar_atalho.py``);
3. a janela (``tag_window``), que também informa o comando de relançamento,
   para que "Fixar na barra de tarefas" a partir da janela aberta reabra o
   MPS-Eval, e não um interpretador Python solto.

Fora do Windows, todas as funções são no-ops.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Formato recomendado pela Microsoft: Empresa.Produto.SubProduto.Versão (até 128 caracteres, sem espaços)
APP_ID = "ITA.MPSEval.Desktop.1"
APP_NAME = "MPS-Eval"
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
ICON_ICO = PACKAGE_DIR / "assets" / "icon" / "mpseval.ico"

IS_WINDOWS = sys.platform == "win32"


def in_venv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def gui_python(env_dir: Path, windows: bool | None = None) -> Path:
    """Interpretador "sem console" de um ambiente: Scripts\\pythonw.exe no Windows, bin/python nos demais."""
    env_dir = Path(env_dir)
    if windows is None:
        windows = IS_WINDOWS
    if windows:
        pyw = env_dir / "Scripts" / "pythonw.exe"
        return pyw if pyw.exists() else env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def launch_command(python: Path | str | None = None) -> tuple[str, str, str]:
    """(executável, argumentos, pasta de trabalho) usados pelo atalho e pelo relançamento.

    * Executável congelado (PyInstaller): o próprio .exe, sem argumentos.
    * ``python`` informado: esse interpretador roda ``-m mpseval``.
    * Caso contrário: o pythonw do ambiente atual (o venv em uso), sem janela de console.
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return str(exe), "", str(exe.parent)
    if python is not None:
        return str(python), "-m mpseval", str(PROJECT_DIR)
    if in_venv():
        exe = gui_python(Path(sys.prefix))
    else:
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        if IS_WINDOWS and pythonw.exists():
            exe = pythonw
    return str(exe), "-m mpseval", str(PROJECT_DIR)


def icon_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable          # o ícone fica embutido no .exe (--icon do PyInstaller)
    return str(ICON_ICO)


def set_process_app_id() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        return True
    except (AttributeError, OSError):
        return False


def tag_window(hwnd: int) -> bool:
    """Grava AUMID e comando de relançamento na janela (requer pywin32)."""
    if not IS_WINDOWS:
        return False
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon
    except ImportError:
        return False
    exe, args, _ = launch_command()
    command = f'"{exe}" {args}'.strip()
    try:
        store = propsys.SHGetPropertyStoreForWindow(hwnd, propsys.IID_IPropertyStore)
        for key, value in (
            (pscon.PKEY_AppUserModel_ID, APP_ID),
            (pscon.PKEY_AppUserModel_RelaunchCommand, command),
            (pscon.PKEY_AppUserModel_RelaunchDisplayNameResource, APP_NAME),
            (pscon.PKEY_AppUserModel_RelaunchIconResource, f"{icon_path()},0"),
        ):
            store.SetValue(key, propsys.PROPVARIANTType(value, pythoncom.VT_LPWSTR))
        store.Commit()
        return True
    except Exception:  # noqa: BLE001 - integração cosmética, nunca deve derrubar o app
        return False
