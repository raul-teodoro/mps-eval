"""Cria os atalhos do MPS-Eval no Windows, presos ao venv que executou este script.

Uso, na pasta do projeto:

    .venv\\Scripts\\python criar_atalho.py          (ou: ative o venv e rode  python criar_atalho.py)

O venv que roda este script passa a ser o venv que o atalho usa para abrir o
app (via pythonw.exe, sem janela de console). Antes de criar, o script confere
se esse venv tem o PyQt6 e o pywin32 instalados.

Opções:
    --python CAMINHO   usa outro venv (pasta do venv ou o python.exe dele)
    --exe CAMINHO      aponta para o executável gerado pelo PyInstaller
    --sem-desktop      não cria atalho na Área de Trabalho
    --sem-menu         não cria atalho no Menu Iniciar
    --verificar        só mostra o que seria feito, sem criar nada
    --remover          remove os atalhos

Os atalhos levam o AppUserModelID do app, então janela e atalho fixado viram um
único ícone na barra de tarefas. Fixar por código não é permitido pelo Windows:
clique com o botão direito no atalho do Menu Iniciar > Fixar na barra de tarefas.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from mpseval.windows import APP_ID, APP_NAME, ICON_ICO, IS_WINDOWS, gui_python  # noqa: E402

DESCRIPTION = "Avaliação de conformidade MPS.BR — Nível G (GPR e REQ)"
VENV_NAMES = (".venv", "venv", "env")


# ------------------------------------------------------------------ escolha do ambiente
@dataclass
class Target:
    exe: Path            # o que o atalho executa
    args: str
    workdir: Path
    icon: Path
    env_dir: Path | None  # venv associado (None para o .exe congelado)
    origin: str           # explicação para o usuário


def env_dir_from_python(python: Path) -> Path:
    """Pasta do venv a partir de .../Scripts/python.exe ou .../bin/python (ou da própria pasta)."""
    python = Path(python)
    if python.is_dir():
        return python
    return python.parent.parent


def is_venv(env_dir: Path) -> bool:
    return (Path(env_dir) / "pyvenv.cfg").exists()


def resolve_target(python_arg: str | None = None, exe_arg: str | None = None, *,
                   prefix: str = sys.prefix, base_prefix: str = getattr(sys, "base_prefix", sys.prefix),
                   project: Path = PROJECT_DIR, windows: bool | None = None) -> Target:
    windows = IS_WINDOWS if windows is None else windows
    if exe_arg:
        exe = Path(exe_arg).resolve()
        if not exe.exists():
            raise SystemExit(f"Executável não encontrado: {exe}")
        return Target(exe, "", exe.parent, exe, None, "executável informado em --exe")

    if python_arg:
        env = env_dir_from_python(Path(python_arg).resolve())
        origin = "venv informado em --python"
    elif prefix != base_prefix:
        env = Path(prefix)
        origin = "venv que está executando este script"
    else:
        found = [project / n for n in VENV_NAMES if is_venv(project / n)]
        if not found:
            raise SystemExit(
                "Este script não está rodando dentro de um venv e não há .venv na pasta do projeto.\n"
                "Crie e use o venv do app, por exemplo:\n"
                "    python -m venv .venv\n"
                "    .venv\\Scripts\\python -m pip install -r requirements.txt\n"
                "    .venv\\Scripts\\python criar_atalho.py")
        env = found[0]
        origin = f"venv encontrado na pasta do projeto ({env.name})"

    if not is_venv(env):
        raise SystemExit(f"{env} não parece ser um venv (falta o arquivo pyvenv.cfg).")
    exe = gui_python(env, windows)
    if not exe.exists():
        raise SystemExit(f"Interpretador não encontrado no venv: {exe}")
    return Target(exe, "-m mpseval", project, ICON_ICO, env, origin)


def console_python(env_dir: Path, windows: bool | None = None) -> Path:
    windows = IS_WINDOWS if windows is None else windows
    return env_dir / ("Scripts/python.exe" if windows else "bin/python")


def check_env(target: Target) -> list[str]:
    """Confere, no próprio venv, se o app consegue abrir. Retorna os problemas encontrados."""
    if target.env_dir is None:
        return []
    py = console_python(target.env_dir)
    code = ("import importlib.util as u, sys;"
            "mods = ['PyQt6.QtWidgets', 'mpseval'] + (['win32com'] if sys.platform == 'win32' else []);"
            "print(','.join(m for m in mods if u.find_spec(m.split('.')[0]) is None))")
    try:
        out = subprocess.run([str(py), "-c", code], cwd=target.workdir, capture_output=True, text=True,
                             timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [f"não foi possível executar {py}: {e}"]
    if out.returncode != 0:
        return [f"o Python do venv falhou: {out.stderr.strip()[:300]}"]
    missing = [m for m in out.stdout.strip().split(",") if m]
    return [f"falta o pacote {m}" for m in missing]


# ------------------------------------------------------------------ atalhos
def shortcut_locations(desktop: bool = True, start_menu: bool = True) -> list[Path]:
    out: list[Path] = []
    if start_menu:
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        out.append(appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{APP_NAME}.lnk")
    if desktop:
        out.append(_desktop_dir() / f"{APP_NAME}.lnk")
    return out


def _desktop_dir() -> Path:
    """Área de Trabalho real (respeita redirecionamento para o OneDrive)."""
    if IS_WINDOWS:
        try:
            from win32com.shell import shell, shellcon
            return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))
        except Exception:  # noqa: BLE001
            pass
    return Path.home() / "Desktop"


def create_shortcut(lnk: Path, t: Target) -> None:
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell

    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                      shell.IID_IShellLink)
    link.SetPath(str(t.exe))
    link.SetArguments(t.args)
    link.SetWorkingDirectory(str(t.workdir))
    link.SetDescription(DESCRIPTION)
    link.SetIconLocation(str(t.icon), 0)

    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()

    lnk.parent.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(lnk), 0)


def describe(t: Target) -> str:
    lines = [f"Ambiente:  {t.env_dir or '—'}  ({t.origin})",
             f"Comando:   \"{t.exe}\" {t.args}".rstrip(),
             f"Pasta:     {t.workdir}",
             f"Ícone:     {t.icon}",
             f"App ID:    {APP_ID}"]
    return "\n".join(lines)


# ------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python criar_atalho.py",
                                description="Cria os atalhos do MPS-Eval presos ao venv atual.")
    p.add_argument("--python", metavar="CAMINHO", help="pasta de outro venv, ou o python.exe dele")
    p.add_argument("--exe", metavar="CAMINHO", help="executável do PyInstaller, em vez de um venv")
    p.add_argument("--sem-desktop", action="store_true", help="não criar atalho na Área de Trabalho")
    p.add_argument("--sem-menu", action="store_true", help="não criar atalho no Menu Iniciar")
    p.add_argument("--verificar", action="store_true", help="só mostrar o que seria feito")
    p.add_argument("--remover", action="store_true", help="remover os atalhos")
    a = p.parse_args(argv)

    locations = shortcut_locations(desktop=not a.sem_desktop, start_menu=not a.sem_menu)

    if a.remover:
        for lnk in locations:
            if lnk.exists():
                lnk.unlink()
                print(f"Removido:  {lnk}")
        return 0

    target = resolve_target(a.python, a.exe)
    print(describe(target))
    problems = check_env(target)
    if problems:
        py = console_python(target.env_dir) if target.env_dir else "python"
        print("\nO venv escolhido não consegue abrir o app:")
        for pr in problems:
            print(f"  - {pr}")
        print(f"\nInstale as dependências nele e rode de novo:\n    \"{py}\" -m pip install -r requirements.txt")
        return 1
    if target.env_dir is not None:
        print("\nVenv conferido: PyQt6" + (" e pywin32 instalados." if IS_WINDOWS else " instalado."))

    if a.verificar:
        print("\nAtalhos que seriam criados:")
        for lnk in locations:
            print(f"  {lnk}")
        return 0
    if not IS_WINDOWS:
        print("\nA criação de atalhos só funciona no Windows.")
        return 1
    try:
        import pythoncom  # noqa: F401
    except ImportError:
        print("\nO Python que roda este script não tem o pywin32. Rode o script com o Python do venv.")
        return 1
    if not ICON_ICO.exists() and target.env_dir is not None:
        print(f"\nÍcone não encontrado em {ICON_ICO}")
        return 1

    print()
    for lnk in locations:
        create_shortcut(lnk, target)
        print(f"Criado:    {lnk}")
    print("\nPara fixar: botão direito no atalho do Menu Iniciar > Fixar na barra de tarefas.")
    print("Se o venv mudar de lugar ou for recriado, rode este script de novo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
