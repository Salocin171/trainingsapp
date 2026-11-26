"""Autostart (Hintergrunddienst) aus der App heraus einrichten – führt autostart.command für genau diesen Ordner aus.

Das Skript beendet dabei den laufenden Server und startet ihn als LaunchAgent neu. Deshalb läuft es als eigener
Prozess in einer eigenen Sitzung: launchd beendet beim Stoppen des alten Dienstes dessen ganze Prozessgruppe.
"""
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from . import config
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


def status() -> dict:
    folder = _folder_of_service()
    return {
        "supported": sys.platform == "darwin",
        "installed": folder is not None,
        "this_folder": folder == config.ROOT.resolve(),
        # Läuft dieser Server als der Dienst? (mit --reload ist der Dienst der Elternprozess)
        "active": _service_pid() in (os.getpid(), os.getppid()) if folder else False,
        "folder": str(config.ROOT), "log": str(LOG), "started": STARTED,
    }


def install() -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("Autostart gibt es nur auf dem Mac.")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w") as log:
        subprocess.Popen(["/bin/zsh", str(config.ROOT / "autostart.command"), "--from-app"], cwd=config.ROOT,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return {"started": True, "log": str(LOG)}
