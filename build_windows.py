"""Gera o instalador do MPS-Eval para Windows: dist\\MPS-Eval-Setup-<versão>.exe

Uso (no Windows, na pasta do projeto, com o venv ativo):

    python -m pip install -r requirements.txt -r requirements-build.txt
    python build_windows.py

Etapas:
  1. Gera as propriedades do .exe (nome, versão, empresa).
  2. Empacota o app com o PyInstaller em dist\\MPS-Eval\\ (Python e PyQt6 inclusos).
  3. Abre o executável em modo de autoteste para confirmar que ele inicia.
  4. Compila o instalador com o Inno Setup (ISCC.exe).

Opções:
    --sem-instalador   para na etapa 2 (só a pasta dist\\MPS-Eval)
    --pular-teste      não roda o autoteste do executável
    --iscc CAMINHO     caminho do ISCC.exe, se não estiver no lugar padrão
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGING = ROOT / "packaging"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT))

from mpseval import __version__  # noqa: E402

APP_NAME = "MPS-Eval"


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def version_tuple(v: str) -> tuple[int, int, int, int]:
    nums = [int(x) for x in v.split(".") if x.isdigit()][:4]
    return tuple(nums + [0] * (4 - len(nums)))  # type: ignore[return-value]


def write_version_file(path: Path, version: str) -> Path:
    """Arquivo de recursos de versão no formato aceito pelo PyInstaller (--version-file)."""
    t = version_tuple(version)
    path.write_text(f"""# gerado por build_windows.py
VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('041604B0', [
        StringStruct('CompanyName', 'Instituto Tecnológico de Aeronáutica'),
        StringStruct('FileDescription', 'MPS-Eval — Avaliação de conformidade MPS.BR'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', '{APP_NAME}'),
        StringStruct('OriginalFilename', '{APP_NAME}.exe'),
        StringStruct('ProductName', '{APP_NAME}'),
        StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
""", encoding="utf-8")
    return path


def find_iscc(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return Path(found)
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            p = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if p.exists():
                return p
    return None


def run(cmd: list[str], **kw) -> None:
    print("   " + " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python build_windows.py", description="Gera o instalador do MPS-Eval.")
    p.add_argument("--sem-instalador", action="store_true", help="só gera a pasta dist\\MPS-Eval")
    p.add_argument("--pular-teste", action="store_true", help="não roda o autoteste do executável")
    p.add_argument("--iscc", metavar="CAMINHO", help="caminho do ISCC.exe (Inno Setup)")
    a = p.parse_args(argv)

    windows = sys.platform == "win32"
    if not windows:
        print("Aviso: fora do Windows só é possível validar o empacotamento; o instalador não é gerado.")
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix) and not os.environ.get("CI"):
        print("Aviso: você não está num venv. O executável vai incluir o que estiver instalado neste Python.")
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Falta o PyInstaller. Instale com:\n    python -m pip install -r requirements-build.txt")
        return 1

    print(f"MPS-Eval {__version__}  ·  Python {sys.version.split()[0]}  ·  {sys.executable}")

    # 1. propriedades do executável
    step("Gerando propriedades do executável")
    BUILD.mkdir(exist_ok=True)
    vfile = write_version_file(BUILD / "version_info.txt", __version__)
    env = dict(os.environ, MPSEVAL_VERSION_FILE=str(vfile))

    # 2. PyInstaller
    step("Empacotando com o PyInstaller")
    run([sys.executable, "-m", "PyInstaller", str(PACKAGING / "mpseval.spec"), "--noconfirm", "--clean",
         "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller")], cwd=ROOT, env=env)
    exe = DIST / APP_NAME / (f"{APP_NAME}.exe" if windows else APP_NAME)
    if not exe.exists():
        print(f"Executável não encontrado em {exe}")
        return 1
    size = sum(f.stat().st_size for f in (DIST / APP_NAME).rglob("*") if f.is_file()) / 1e6
    print(f"   {exe}  ({size:.0f} MB na pasta)")

    # 3. autoteste
    if not a.pular_teste:
        step("Autoteste do executável (abre e fecha sozinho)")
        with tempfile.TemporaryDirectory() as tmp:
            test_env = dict(os.environ, MPSEVAL_HOME=tmp)      # não toca no banco real
            if not windows:
                test_env.setdefault("QT_QPA_PLATFORM", "offscreen")
            try:
                r = subprocess.run([str(exe), "--self-test"], env=test_env, timeout=120)
            except subprocess.TimeoutExpired:
                print("   O executável não fechou a tempo.")
                return 1
        if r.returncode != 0:
            print(f"   Falhou (código {r.returncode}). Rode {exe} manualmente para ver o erro.")
            return 1
        print("   OK: abriu, carregou os 30 critérios, o ícone e as fontes, e gerou um PDF.")

    if a.sem_instalador or not windows:
        print(f"\nPronto. Pasta do app: {DIST / APP_NAME}")
        return 0

    # 4. Inno Setup
    step("Compilando o instalador com o Inno Setup")
    iscc = find_iscc(a.iscc)
    if iscc is None:
        print("   Inno Setup não encontrado. Instale a versão 6.3 ou superior:\n"
              "       winget install JRSoftware.InnoSetup\n"
              "   ou baixe em https://jrsoftware.org/isdl.php e rode este script de novo.")
        return 1
    run([str(iscc), f"/DAppVersion={__version__}", str(PACKAGING / "installer.iss")], cwd=PACKAGING)
    setup = DIST / f"{APP_NAME}-Setup-{__version__}.exe"
    if not setup.exists():
        print(f"   Instalador não encontrado em {setup}")
        return 1
    print(f"\nPronto: {setup}  ({setup.stat().st_size / 1e6:.0f} MB)")
    print("Esse único arquivo instala o app, cria os atalhos e o desinstalador.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
