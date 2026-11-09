"""Testes da integração com o Windows e do criar_atalho.py (lógica independente de plataforma)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mpseval import windows  # noqa: E402

spec = importlib.util.spec_from_file_location("criar_atalho", ROOT / "criar_atalho.py")
ca = importlib.util.module_from_spec(spec)
sys.modules["criar_atalho"] = ca
spec.loader.exec_module(ca)


def fake_venv(base: Path, name: str = ".venv") -> Path:
    env = base / name
    (env / "Scripts").mkdir(parents=True)
    (env / "pyvenv.cfg").write_text("home = C:\\Python313\n")
    (env / "Scripts" / "python.exe").write_bytes(b"")
    (env / "Scripts" / "pythonw.exe").write_bytes(b"")
    return env


def test_app_id_formato():
    assert len(windows.APP_ID) <= 128 and " " not in windows.APP_ID


def test_icone_existe():
    assert windows.ICON_ICO.exists() and windows.ICON_ICO.stat().st_size > 1000


def test_reconhece_o_venv_que_executa_o_script(tmp_path):
    env = fake_venv(tmp_path / "proj")
    t = ca.resolve_target(prefix=str(env), base_prefix="C:\\Python313", project=tmp_path / "proj", windows=True)
    assert t.env_dir == env
    assert t.exe == env / "Scripts" / "pythonw.exe"          # sem janela de console
    assert t.args == "-m mpseval" and t.workdir == tmp_path / "proj"
    assert "executando" in t.origin


def test_fora_de_venv_usa_venv_da_pasta(tmp_path):
    proj = tmp_path / "proj"
    env = fake_venv(proj, "venv")
    t = ca.resolve_target(prefix="C:\\Python313", base_prefix="C:\\Python313", project=proj, windows=True)
    assert t.env_dir == env and "pasta do projeto" in t.origin


def test_fora_de_venv_sem_venv_na_pasta_recusa(tmp_path):
    with pytest.raises(SystemExit) as e:
        ca.resolve_target(prefix="/usr", base_prefix="/usr", project=tmp_path, windows=True)
    assert "venv" in str(e.value)


def test_opcao_python_aceita_pasta_ou_executavel(tmp_path):
    env = fake_venv(tmp_path, "outro")
    for arg in (env, env / "Scripts" / "python.exe"):
        t = ca.resolve_target(str(arg), prefix="/usr", base_prefix="/usr", project=tmp_path, windows=True)
        assert t.env_dir == env.resolve() and "--python" in t.origin


def test_pasta_que_nao_e_venv_recusa(tmp_path):
    (tmp_path / "x" / "Scripts").mkdir(parents=True)
    with pytest.raises(SystemExit):
        ca.resolve_target(str(tmp_path / "x"), prefix="/usr", base_prefix="/usr", project=tmp_path, windows=True)


def test_executavel_congelado(tmp_path):
    exe = tmp_path / "MPS-Eval.exe"
    exe.write_bytes(b"")
    t = ca.resolve_target(exe_arg=str(exe), project=tmp_path)
    assert t.exe == exe and t.args == "" and t.env_dir is None and t.icon == exe


def test_check_env_confere_dependencias_no_venv_escolhido(tmp_path):
    """Cria venvs reais: um vazio (deve acusar PyQt6) e um que enxerga o PyQt6 (deve passar)."""
    vazio, completo = tmp_path / "vazio", tmp_path / "completo"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(vazio)], check=True)
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", "--system-site-packages", str(completo)],
                   check=True)
    mk = lambda env: ca.Target(env / "bin" / "python", "-m mpseval", ROOT, windows.ICON_ICO, env, "teste")
    assert any("PyQt6" in p for p in ca.check_env(mk(vazio)))
    assert ca.check_env(mk(completo)) == []


def test_locais_dos_atalhos(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert ca.shortcut_locations(desktop=False) == [
        tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "MPS-Eval.lnk"]


def test_relancamento_da_janela_bate_com_o_atalho(monkeypatch, tmp_path):
    env = fake_venv(tmp_path)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "prefix", str(env))
    monkeypatch.setattr(sys, "base_prefix", "C:\\Python313")
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    exe, args, _ = windows.launch_command()
    t = ca.resolve_target(prefix=str(env), base_prefix="C:\\Python313", project=windows.PROJECT_DIR, windows=True)
    assert Path(exe) == t.exe and args == t.args


def test_noop_fora_do_windows():
    if windows.IS_WINDOWS:
        return
    assert windows.set_process_app_id() is False
    assert windows.tag_window(0) is False
