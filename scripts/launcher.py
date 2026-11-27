"""Starter für Windows – macht, was auf dem Mac Trainingsapp.command, Update.command und autostart.command tun.

Aufgerufen von den .bat-Dateien im App-Ordner (mit irgendeinem installierten Python, die .venv gibt es dann evtl.
noch nicht – deshalb nur Standardbibliothek):

    launcher.py start            Trainingsapp.bat: einrichten, starten, Browser öffnen
    launcher.py update           Update.bat: neueste Version von GitHub holen
    launcher.py autostart [off]  Autostart.bat: als Hintergrunddienst einrichten bzw. entfernen
    launcher.py serve            vom Autostart (Trainingsapp.vbs): Server ohne Fenster betreiben
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import winservice  # noqa: E402 – erst nach dem Pfad

MIN_PYTHON = (3, 12)
REPO = "https://github.com/Salocin171/trainingsapp"
PYTHON_URL = "https://www.python.org/downloads/windows/"
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / "Scripts" / "python.exe"
FOLDER_MARK = VENV / "trainingsapp-ordner.txt"      # für welchen Ordner die Umgebung angelegt wurde
REQ_MARK = VENV / "trainingsapp-requirements.txt"   # Prüfsumme der zuletzt installierten requirements.txt
MAX_LOG = 5_000_000


class Abort(Exception):
    """Abbruch mit einer Meldung für den Menschen vor dem Fenster."""


def say(text: str = "") -> None:
    print(text, flush=True)


def pause() -> None:
    try:
        input("\nEnter drücken zum Schließen …")
    except (EOFError, KeyboardInterrupt):
        pass


def port() -> int:
    """PORT aus .env wie in den Mac-Skripten, sonst 8765."""
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("PORT="):
                return int(line.split("=", 1)[1].strip().strip('"').strip("'"))
    except (OSError, ValueError):
        pass
    return 8765


def url() -> str:
    return f"http://127.0.0.1:{port()}"


def child_env(service: bool = False) -> dict:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if service:
        env[winservice.SERVICE_ENV] = "1"
    return env


# --- Python-Umgebung (.venv) ---------------------------------------------------------

def _version_ok(python: str | Path) -> bool:
    try:
        return subprocess.run([str(python), "-c", f"import sys; sys.exit(0 if sys.version_info >= {MIN_PYTHON} else 1)"],
                              capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_python() -> str:
    """Ein Python ab 3.12: das, mit dem der Launcher läuft, sonst über den Python-Launcher `py` eine neuere Version."""
    if sys.version_info >= MIN_PYTHON:
        return sys.executable
    for minor in (14, 13, 12):
        try:
            r = subprocess.run(["py", f"-3.{minor}", "-c", "import sys; print(sys.executable)"],
                               capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            break
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    webbrowser.open(PYTHON_URL)
    raise Abort(
        f"Für die Trainingsapp wird Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} oder neuer gebraucht "
        f"(gefunden: {sys.version.split()[0]}).\n"
        "1. Auf der Seite, die sich gerade öffnet, „Download Python“ klicken und den Installer starten.\n"
        "2. Im Installer unten „Add python.exe to PATH“ anhaken, dann „Install Now“.\n"
        "3. Danach Trainingsapp.bat noch einmal doppelklicken.")


def _requirements_hash() -> str:
    return hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()


def _venv_ok() -> bool:
    if not VENV_PYTHON.exists():
        return False
    try:
        folder = FOLDER_MARK.read_text(encoding="utf-8").strip()
    except OSError:
        folder = ""
    if folder and not winservice.same_folder(Path(folder), ROOT):
        say("Der App-Ordner wurde verschoben – Python-Umgebung wird neu eingerichtet …")
        return False
    if not _version_ok(VENV_PYTHON):
        say("Python-Umgebung ist zu alt oder beschädigt – wird neu angelegt …")
        return False
    return True


def packages_outdated() -> bool:
    try:
        return REQ_MARK.read_text(encoding="utf-8").strip() != _requirements_hash()
    except OSError:
        return True


def ensure_venv() -> bool:
    """.venv anlegen (falls nötig) und Pakete installieren, wenn sich requirements.txt geändert hat.
    True = es wurde etwas installiert."""
    if VENV.exists() and not _venv_ok():
        shutil.rmtree(VENV, ignore_errors=True)
    if not VENV_PYTHON.exists():
        python = find_python()
        say("Erster Start: Python-Umgebung wird eingerichtet – dauert ca. eine Minute …")
        if subprocess.run([python, "-m", "venv", str(VENV)]).returncode:
            raise Abort("Einrichten der Python-Umgebung fehlgeschlagen.")
        FOLDER_MARK.write_text(str(ROOT), encoding="utf-8")
        subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q", "--upgrade", "pip"], env=child_env())
    if not packages_outdated():
        return False
    say("Pakete werden installiert …")
    r = subprocess.run([str(VENV_PYTHON), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")],
                       env=child_env())
    if r.returncode:
        raise Abort("Pakete konnten nicht installiert werden (Internet? Läuft die App noch in einem anderen Fenster?).")
    REQ_MARK.write_text(_requirements_hash(), encoding="utf-8")
    return True


def uvicorn_cmd() -> list[str]:
    # --reload: neuer Code (z. B. nach einem Update aus der App) wird ohne Neustart übernommen
    return [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port()),
            "--reload", "--reload-dir", "app"]


# --- Dienst (Autostart) ----------------------------------------------------------------

def _start_service_and_wait() -> bool:
    winservice.start_service()
    return winservice.wait_until(lambda: winservice.app_running(port()), 90)


def autostart(args: list[str]) -> int:
    if args[:1] == ["off"]:
        winservice.uninstall()
        if winservice.server_info(port()).get("mode") == "service":
            winservice.stop(port())
        say("Autostart entfernt. Starten wieder per Doppelklick auf Trainingsapp.bat.")
        pause()
        return 0
    ensure_venv()
    winservice.install(ROOT)
    # Der Dienst beendet beim Start selbst einen Server, der noch in einem Fenster läuft (siehe serve)
    say("Hintergrunddienst wird eingerichtet …")
    if winservice.server_info(port()).get("mode") == "service":
        winservice.stop(port())
    if not _start_service_and_wait():
        raise Abort(f"Der Dienst ist nicht gestartet. Details im Log: {winservice.log_path()}")
    say(f"✔ Trainingsapp läuft im Hintergrund auf {url()} und startet ab jetzt beim Anmelden "
        f"(Log: {winservice.log_path()}).")
    webbrowser.open(url())
    return 0


def serve(_args: list[str]) -> int:
    """Läuft ohne Fenster (Autostart): Server betreiben, Ausgaben ins Log, nach einem Absturz neu starten."""
    log_file = winservice.log_path()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if log_file.exists() and log_file.stat().st_size > MAX_LOG:
        log_file.replace(log_file.with_suffix(".old.log"))
    with log_file.open("a", encoding="utf-8", errors="replace") as log:
        sys.stdout = sys.stderr = log
        p = port()
        say(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} Dienst startet für {ROOT} auf Port {p}")
        info = winservice.server_info(p)
        if info.get("mode") == "service":
            say("Dienst läuft schon – nichts zu tun.")
            return 0
        if winservice.port_in_use(p):
            time.sleep(2)  # der App, die den Dienst gerade eingerichtet hat, Zeit für ihre Antwort lassen
            if not winservice.stop(p):
                say(f"Port {p} ist belegt (von einem anderen Programm?) – Dienst beendet.")
                return 1
        winservice.remember_server(p, ROOT, "service")
        crashes: list[float] = []
        try:
            while True:
                code = subprocess.run(uvicorn_cmd(), cwd=ROOT, env=child_env(service=True), stdin=subprocess.DEVNULL,
                                      stdout=log, stderr=subprocess.STDOUT).returncode
                now = time.monotonic()
                crashes = [t for t in crashes if now - t < 600] + [now]
                say(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} Server beendet (Code {code})")
                if len(crashes) >= 5:
                    say("Zu viele Abstürze in 10 Minuten – Dienst gibt auf. Neu starten: Trainingsapp.bat.")
                    return 1
                time.sleep(3)
        finally:
            winservice.forget_server(p)


# --- Start ---------------------------------------------------------------------------

def start(_args: list[str]) -> int:
    p = port()
    folder = winservice.folder_of_service()
    if folder is not None and not winservice.same_folder(folder, ROOT):
        say("Die App wurde verschoben – Hintergrunddienst wird für diesen Ordner neu eingerichtet …")
        return autostart([])
    if folder is not None:  # Autostart eingerichtet: nur öffnen, kein zweiter Server
        if packages_outdated() and winservice.server_info(p).get("mode") == "service":
            winservice.stop(p)  # neue Pakete: Dienst anhalten, damit pip keine geöffneten Dateien ersetzen muss
        ensure_venv()
        if not winservice.app_running(p) and not _start_service_and_wait():
            raise Abort(f"Der Hintergrunddienst startet nicht. Details im Log: {winservice.log_path()}")
        webbrowser.open(url())
        return 0
    if winservice.app_running(p):
        say(f"Die Trainingsapp läuft schon ({url()}) – öffne den Browser.")
        webbrowser.open(url())
        return 0
    if winservice.port_in_use(p):
        raise Abort(f"Port {p} ist von einem anderen Programm belegt. Anderen Port in .env setzen (PORT=8766).")
    ensure_venv()
    say(f"Trainingsapp läuft auf {url()}  (Beenden: Fenster schließen oder Strg+C)")
    threading.Timer(1.5, webbrowser.open, [url()]).start()
    winservice.remember_server(p, ROOT, "window")
    proc = subprocess.Popen(uvicorn_cmd(), cwd=ROOT, env=child_env())
    try:
        return proc.wait()
    except KeyboardInterrupt:  # Strg+C erreicht auch den Server; auf sein Ende warten
        return proc.wait()
    finally:
        winservice.forget_server(p)


# --- Update ----------------------------------------------------------------------------

def _git(*args: str) -> bool:
    return subprocess.run(["git", *args], cwd=ROOT).returncode == 0


def _update_from_zip() -> None:
    """Ohne git: aktuelle Version als ZIP laden und die App-Dateien ersetzen (data/, .venv/, .env bleiben)."""
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "app.zip"
        try:
            urllib.request.urlretrieve(f"{REPO}/archive/refs/heads/main.zip", archive)
            with zipfile.ZipFile(archive) as z:
                z.extractall(tmp)
        except (OSError, zipfile.BadZipFile) as e:
            raise Abort(f"Update nicht möglich (keine Verbindung zu GitHub?): {e}") from None
        copy_tree(Path(tmp) / "trainingsapp-main", ROOT)


def copy_tree(src: Path, dst: Path, keep: tuple[str, ...] = ("data", ".venv", ".git", ".env")) -> None:
    for item in src.iterdir():
        if item.name in keep:
            continue
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def update(_args: list[str]) -> int:
    say("Hole die neueste Version der Trainingsapp …")
    if (ROOT / ".git").exists():
        if not shutil.which("git"):
            raise Abort("Für das Update wird git gebraucht (https://git-scm.com/download/win).")
        if not _git("pull", "--ff-only"):
            raise Abort("Update nicht möglich – vermutlich wurden Dateien der App von Hand geändert.")
    elif shutil.which("git"):
        # Als ZIP geladen, git ist da: Ordner einmalig mit GitHub verbinden – künftige Updates gehen dann auch aus
        # der App heraus. data/ und .venv/ stehen in .gitignore und bleiben unberührt.
        ok = (_git("init", "-q") and _git("remote", "add", "origin", f"{REPO}.git")
              and _git("fetch", "-q", "origin", "main") and _git("checkout", "-q", "-f", "-B", "main", "origin/main"))
        if not ok:
            shutil.rmtree(ROOT / ".git", ignore_errors=True)
            raise Abort("Update nicht möglich (keine Verbindung zu GitHub?).")
    else:
        _update_from_zip()

    p = port()
    service = winservice.server_info(p).get("mode") == "service"
    if service:
        winservice.stop(p)  # Dienst anhalten: pip kann sonst geöffnete Dateien nicht ersetzen
    ensure_venv()
    folder = winservice.folder_of_service()
    if folder is not None and not winservice.same_folder(folder, ROOT):
        say("Hintergrunddienst zeigt noch auf einen anderen Ordner – wird für diesen Ordner neu eingerichtet …")
        autostart([])
    elif folder is not None:
        _start_service_and_wait()
    say("\nFertig. Läuft die App gerade in einem Fenster, dort Strg+C drücken und Trainingsapp.bat neu starten;\n"
        "sonst einfach den Browser neu laden.")
    pause()
    return 0


COMMANDS = {"start": start, "update": update, "autostart": autostart, "serve": serve}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        say(__doc__)
        return 2
    for stream in (sys.stdout, sys.stderr):  # Umlaute auch in Fenstern mit alter Codepage
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    try:
        return COMMANDS[argv[0]](argv[1:])
    except Abort as e:
        say(f"\n{e}\nDeine Trainingsdaten sind davon nicht betroffen.")
        if argv[0] != "serve":
            pause()
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
