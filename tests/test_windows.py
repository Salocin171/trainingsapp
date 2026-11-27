"""Windows-Teil: Starter (scripts/launcher.py), Autostart-Eintrag (app/winservice.py), Pfade. Läuft auf jedem
System – Prozesse und Windows-APIs werden nicht angefasst."""
import importlib.util
import sys
from pathlib import Path

import pytest

from app import autostart, config, winservice

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def launcher():
    spec = importlib.util.spec_from_file_location("launcher", ROOT / "scripts" / "launcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def windows_dirs(tmp_path, monkeypatch):
    """APPDATA / LOCALAPPDATA in einen Testordner umleiten."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    return tmp_path


def test_venv_python_per_platform(tmp_path):
    assert config.venv_python(tmp_path, windows=True) == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert config.venv_python(tmp_path, windows=False) == tmp_path / ".venv" / "bin" / "python"


def test_autostart_entry_knows_its_folder(windows_dirs, monkeypatch):
    folder = windows_dirs / "Jürgen" / "Trainingsapp"  # Umlaut im Pfad (Benutzername)
    assert winservice.folder_of_service() is None
    path = winservice.install(folder)
    assert path.parent.name == "Startup" and path.name == "Trainingsapp.vbs"
    text = path.read_text(encoding="utf-16")
    assert f'shell.CurrentDirectory = "{folder}"' in text
    assert f'shell.Run """{folder / ".venv" / "Scripts" / "python.exe"}"" ""{folder / "scripts" / "launcher.py"}"" serve", 0' in text
    assert winservice.folder_of_service() == folder

    monkeypatch.setattr(config, "IS_WINDOWS", True)
    monkeypatch.delenv(winservice.SERVICE_ENV, raising=False)
    s = autostart.windows_status()
    assert s["installed"] and not s["this_folder"] and not s["active"]
    winservice.install(config.ROOT)
    monkeypatch.setenv(winservice.SERVICE_ENV, "1")
    s = autostart.status()
    assert s["platform"] == "windows" and s["this_folder"] and s["active"]

    winservice.uninstall()
    assert winservice.folder_of_service() is None
    winservice.uninstall()  # zweimal entfernen schadet nicht


def test_server_info_ignores_dead_or_missing_entries(windows_dirs, monkeypatch):
    assert winservice.server_info(8765) == {}
    monkeypatch.setattr(winservice, "_alive", lambda pid: False)
    winservice.remember_server(8765, ROOT, "window")
    assert winservice.server_info(8765) == {}  # Prozess lebt nicht mehr
    monkeypatch.setattr(winservice, "_alive", lambda pid: True)
    assert winservice.server_info(8765)["mode"] == "window"
    winservice.forget_server(8765)
    assert winservice.server_info(8765) == {}


def test_stop_never_kills_when_the_app_is_not_answering(windows_dirs, monkeypatch):
    """Veraltete Prozess-ID (Neustart, ID neu vergeben): nichts beenden, wenn auf dem Port nicht die App läuft."""
    killed = []
    monkeypatch.setattr(winservice, "_alive", lambda pid: True)
    monkeypatch.setattr(winservice, "app_running", lambda port: False)
    monkeypatch.setattr(winservice, "port_in_use", lambda port: False)
    monkeypatch.setattr(winservice.subprocess, "run", lambda cmd, **kw: killed.append(cmd))
    (winservice.state_dir()).mkdir(parents=True)
    (winservice.state_dir() / "server-8765.json").write_text('{"pid": 4242, "mode": "window"}', encoding="utf-8")
    assert winservice.stop(8765) is True and killed == []

    monkeypatch.setattr(winservice, "app_running", lambda port: True)
    assert winservice.stop(8765) is True
    assert killed == [["taskkill", "/PID", "4242", "/T", "/F"]]


def test_launcher_reads_port_from_env_file(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    assert launcher.port() == 8765
    (tmp_path / ".env").write_text("# Kommentar\nPORT=8766\n", encoding="utf-8")
    assert launcher.port() == 8766


def test_launcher_zip_update_keeps_data(launcher, tmp_path):
    """Update ohne git: App-Dateien werden ersetzt, data/, .venv/ und .env bleiben."""
    new, app = tmp_path / "trainingsapp-main", tmp_path / "app"
    (new / "app").mkdir(parents=True)
    (new / "app" / "x.py").write_text("A = 2\n", encoding="utf-8")
    (new / "data").mkdir()
    (new / "data" / "training.db").write_text("leer", encoding="utf-8")
    (app / "app").mkdir(parents=True)
    (app / "app" / "x.py").write_text("A = 1\n", encoding="utf-8")
    (app / "data").mkdir()
    (app / "data" / "training.db").write_text("meine Daten", encoding="utf-8")
    (app / ".env").write_text("PORT=8766\n", encoding="utf-8")

    launcher.copy_tree(new, app)
    assert (app / "app" / "x.py").read_text(encoding="utf-8") == "A = 2\n"
    assert (app / "data" / "training.db").read_text(encoding="utf-8") == "meine Daten"
    assert (app / ".env").read_text(encoding="utf-8") == "PORT=8766\n"


def test_launcher_notices_changed_requirements(launcher, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "REQ_MARK", tmp_path / "mark.txt")
    (tmp_path / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    assert launcher.packages_outdated()
    launcher.REQ_MARK.write_text(launcher._requirements_hash(), encoding="utf-8")
    assert not launcher.packages_outdated()
    (tmp_path / "requirements.txt").write_text("fastapi\nhttpx\n", encoding="utf-8")
    assert launcher.packages_outdated()


def test_launcher_uses_running_python_when_new_enough(launcher):
    if sys.version_info >= launcher.MIN_PYTHON:
        assert launcher.find_python() == sys.executable


def test_meta_tells_the_platform():
    from fastapi.testclient import TestClient
    from app.main import app
    meta = TestClient(app).get("/api/meta").json()
    assert meta["platform"] in ("mac", "windows", "other")
    assert meta["mac_calendar"] is (meta["platform"] == "mac")


def test_batch_files_are_ascii():
    """cmd.exe liest .bat in der OEM-Codepage – Umlaute würden verstümmelt; die Texte kommen aus launcher.py."""
    for bat in [*ROOT.glob("*.bat"), *ROOT.glob("scripts/*.bat")]:
        bat.read_bytes().decode("ascii")
