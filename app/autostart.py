"""Autostart (Hintergrunddienst) aus der App heraus einrichten – für genau diesen Ordner.

Mac: führt autostart.command aus. Das Skript beendet dabei den laufenden Server und startet ihn als LaunchAgent neu.
Deshalb läuft es als eigener Prozess in einer eigenen Sitzung: launchd beendet beim Stoppen des alten Dienstes dessen
ganze Prozessgruppe.

Windows: Eintrag im Autostart-Ordner (winservice.py) schreiben und den Dienst starten; der Dienst löst einen Server,
der noch im Fenster läuft (Trainingsapp.bat), selbst ab.
"""
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from . import config, winservice
from .updater import STARTED

LABEL = "de.trainingsapp"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = Path.home() / "Library" / "Logs" / "trainingsapp-autostart.log"


def _folder_of_service() -> Path | None:
    try:
        with PLIST.open("rb") as f:
            return Path(plistlib.load(f)["WorkingDirectory"]).resolve()
    except (OSError, KeyError, plistlib.InvalidFileException):
        return None


def _service_pid() -> int | None:
    try:
        out = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    pid = re.search(r"^\s*pid = (\d+)", out, re.M)
    return int(pid[1]) if pid else None


def mac_status() -> dict:
    folder = _folder_of_service()
    return {
        "supported": True, "platform": "mac",
        "installed": folder is not None,
        "this_folder": folder == config.ROOT.resolve(),
        # Läuft dieser Server als der Dienst? (mit --reload ist der Dienst der Elternprozess)
        "active": _service_pid() in (os.getpid(), os.getppid()) if folder else False,
        "folder": str(config.ROOT), "log": str(LOG), "started": STARTED,
    }


def windows_status() -> dict:
    folder = winservice.folder_of_service()
    this_folder = winservice.same_folder(folder, config.ROOT)
    return {
        "supported": True, "platform": "windows",
        "installed": folder is not None,
        "this_folder": this_folder,
        # Der Dienst (launcher.py serve) setzt die Umgebungsvariable für seinen Server
        "active": this_folder and os.environ.get(winservice.SERVICE_ENV) == "1",
        "folder": str(config.ROOT), "log": str(winservice.log_path()), "started": STARTED,
    }


def status() -> dict:
    if config.IS_WINDOWS:
        return windows_status()
    if config.IS_MAC:
        return mac_status()
    return {"supported": False, "platform": sys.platform, "installed": False, "this_folder": False, "active": False,
            "folder": str(config.ROOT), "log": "", "started": STARTED}


def install() -> dict:
    if config.IS_WINDOWS:
        if not config.venv_python(config.ROOT, windows=True).exists():
            raise RuntimeError("Python-Umgebung (.venv) fehlt – bitte einmal Trainingsapp.bat doppelklicken.")
        already = windows_status()["active"]
        winservice.install(config.ROOT)
        if already:  # dieser Server ist schon der Dienst: Eintrag erneuert, kein Neustart nötig
            return {"started": True, "restart": False, "log": str(winservice.log_path())}
        winservice.start_service()
        return {"started": True, "log": str(winservice.log_path())}
    if not config.IS_MAC:
        raise RuntimeError("Autostart gibt es nur auf dem Mac und unter Windows.")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8") as log:
        subprocess.Popen(["/bin/zsh", str(config.ROOT / "autostart.command"), "--from-app"], cwd=config.ROOT,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return {"started": True, "log": str(LOG)}
