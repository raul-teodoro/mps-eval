# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller para o MPS-Eval (modo pasta, "onedir").

Gera dist/MPS-Eval/ com MPS-Eval.exe e as bibliotecas. O modo pasta abre mais
rápido e gera menos falsos positivos de antivírus que o "onefile"; quem vira um
arquivo único é o instalador (installer.iss).

Uso direto:  pyinstaller packaging/mpseval.spec --noconfirm
(normalmente chamado por build_windows.py)
"""
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ICON = ROOT / "mpseval" / "assets" / "icon" / "mpseval.ico"
VERSION_FILE = os.environ.get("MPSEVAL_VERSION_FILE") if sys.platform == "win32" else None

a = Analysis(
    [str(ROOT / "run_mpseval.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "mpseval" / "data"), "mpseval/data"),
        (str(ROOT / "mpseval" / "assets"), "mpseval/assets"),
    ],
    hiddenimports=["PyQt6.QtSvg", "openpyxl"],
    excludes=[
        "tkinter", "unittest", "pytest", "PIL",
        "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuickWidgets", "PyQt6.QtMultimedia",
        "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtBluetooth", "PyQt6.QtNfc",
        "PyQt6.QtPositioning", "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.Qt3DCore",
    ],
    noarchive=False,
)
# Remove o que o app não usa: traduções do Qt (diálogos de arquivo no Windows são os nativos)
# e o leitor de PDF do Qt (o relatório é gerado por QPdfWriter, que fica no QtGui).
_DROP = ("Qt6Pdf", "qpdf", "/translations/", "\\translations\\")
a.binaries = [b for b in a.binaries if not any(k in b[0] or k in b[1] for k in _DROP)]
a.datas = [d for d in a.datas if not any(k in d[0] or k in d[1] for k in _DROP)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MPS-Eval",
    console=False,                      # app de janela, sem console preto
    icon=str(ICON) if sys.platform == "win32" else None,
    version=VERSION_FILE,               # propriedades do arquivo no Windows (nome, versão)
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="MPS-Eval", upx=False)
