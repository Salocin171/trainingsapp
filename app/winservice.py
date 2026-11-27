"""Hintergrunddienst unter Windows – das Gegenstück zum LaunchAgent auf dem Mac (autostart.command).

Eingerichtet wird ohne Administratorrechte über den Autostart-Ordner des Benutzers: Dort liegt Trainingsapp.vbs und
startet beim Anmelden `scripts/launcher.py serve` ohne Fenster. Der Launcher startet den Server (uvicorn), schreibt
das Log und startet ihn nach einem Absturz neu.

Jeder Launcher, der einen Server startet (im Fenster oder als Dienst), hinterlegt seine Prozess-ID in
%LOCALAPPDATA%\\Trainingsapp\\server-<port>.json – darüber lässt sich der Server später gezielt beenden, z. B. wenn
der Dienst einen im Fenster laufenden Server ablöst.

Nur Standardbibliothek: wird auch vom Launcher benutzt, bevor die Python-Umgebung (.venv) existiert.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

NAME = "Trainingsapp"
SERVICE_ENV = "TRAININGSAPP_SERVICE"  # vom Dienst gesetzt – so weiß der Server, dass er der Dienst ist
FOLDER_PREFIX = "' Ordner: "


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def state_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / NAME


def vbs_path() -> Path:
    return startup_dir() / f"{NAME}.vbs"


def log_path() -> Path:
    return state_dir() / "trainingsapp.log"


def _pid_file(port: int) -> Path:
    return state_dir() / f"server-{port}.json"


# --- Autostart-Eintrag -----------------------------------------------------------

def vbs_text(root: Path) -> str:
    """Skript für den Autostart-Ordner: startet den Launcher im App-Ordner, ohne Fenster (Fensterstil 0)."""
    python = root / ".venv" / "Scripts" / "python.exe"
    launcher = root / "scripts" / "launcher.py"
    quoted = lambda p: f'""{p}""'  # noqa: E731 – in VBScript steht "" für ein Anführungszeichen im Text
    return "\r\n".join([
        "' Trainingsapp: startet die App beim Anmelden im Hintergrund (eingerichtet mit Autostart.bat).",
        "' Abschalten: Autostart.bat off im App-Ordner – oder diese Datei löschen.",
        f"{FOLDER_PREFIX}{root}",
        'Set shell = CreateObject("WScript.Shell")',
        f'shell.CurrentDirectory = "{root}"',
        f'shell.Run "{quoted(python)} {quoted(launcher)} serve", 0, False',
        "",
    ])


def folder_of_service() -> Path | None:
    """App-Ordner, für den der Autostart eingerichtet ist (None = nicht eingerichtet)."""
    try:
        text = vbs_path().read_text(encoding="utf-16")
    except (OSError, UnicodeError):
        return None
    for line in text.splitlines():
        if line.startswith(FOLDER_PREFIX):
            return Path(line[len(FOLDER_PREFIX):].strip())
    return None


def same_folder(a: Path | None, b: Path) -> bool:
    if a is None:
        return False
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return False


def install(root: Path) -> Path:
    """Autostart-Eintrag für diesen App-Ordner schreiben (ersetzt einen alten). UTF-16, damit Pfade mit Umlauten
    (z. B. C:\\Users\\Jürgen) in VBScript ankommen."""
    startup_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)
    vbs_path().write_text(vbs_text(root), encoding="utf-16")
    return vbs_path()


def uninstall() -> None:
    try:
        vbs_path().unlink()
    except FileNotFoundError:
        pass


def start_service() -> None:
    """Dienst jetzt starten (wie beim Anmelden). Losgelöst vom aufrufenden Prozess, damit er ihn überlebt."""
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["wscript.exe", str(vbs_path())], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- Laufende Server ---------------------------------------------------------------

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def app_running(port: int) -> bool:
    """Antwortet auf dem Port die Trainingsapp (und nicht irgendein anderes Programm)?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/meta", timeout=3) as r:
            return r.status == 200 and "race_types" in json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return False


def wait_until(check, seconds: float, step: float = 0.5) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(step)
    return check()


def remember_server(port: int, root: Path, mode: str) -> None:
    """Dieser Prozess (Launcher) betreibt den Server auf `port` – mode: "window" oder "service"."""
    state_dir().mkdir(parents=True, exist_ok=True)
    _pid_file(port).write_text(json.dumps({"pid": os.getpid(), "folder": str(root), "mode": mode}), encoding="utf-8")


def forget_server(port: int) -> None:
    try:
        if json.loads(_pid_file(port).read_text(encoding="utf-8")).get("pid") == os.getpid():
            _pid_file(port).unlink()
    except (OSError, ValueError):
        pass


def server_info(port: int) -> dict:
    """Wer betreibt den Server auf `port`? {} = keiner von uns bekannt (oder der Prozess lebt nicht mehr)."""
    try:
        info = json.loads(_pid_file(port).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return info if _alive(int(info.get("pid", 0))) else {}


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    import ctypes  # nur Windows
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def stop(port: int) -> bool:
    """Den von einem Launcher gestarteten Server auf `port` beenden (samt Unterprozessen). True = Port ist frei."""
    info = server_info(port)
    pid = int(info.get("pid", 0))
    # Nur wenn dort wirklich die App antwortet – eine veraltete Datei könnte sonst einen fremden Prozess treffen
    if pid and pid != os.getpid() and app_running(port):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        try:
            _pid_file(port).unlink()
        except OSError:
            pass
    return wait_until(lambda: not port_in_use(port), 10)
