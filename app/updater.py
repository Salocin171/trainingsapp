"""Updates aus der App heraus: prüfen, ob es auf GitHub neue Commits gibt, und sie auf Knopfdruck holen.

Geht nur mit .git-Ordner (geklont oder einmal per Update.command / Update.bat mit GitHub verbunden). Neue Pakete werden
vor dem Wechsel installiert; den neuen Code lädt der Server dank --reload selbst (Trainingsapp.command bzw. .bat,
Autostart).
"""
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import config

BRANCH = "main"
REMOTE = f"origin/{BRANCH}"
CHECK_EVERY = 30 * 60  # Sekunden zwischen zwei Abfragen bei GitHub
STARTED = time.time()  # Startzeit dieses Servers – die Oberfläche erkennt daran den Neustart nach dem Update

_cache: dict = {"at": 0.0, "status": None}
_lock = threading.Lock()


class UpdateError(RuntimeError):
    pass


def _git(*args: str, timeout: int = 30) -> str:
    r = subprocess.run(["git", *args], cwd=config.ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    if r.returncode:
        raise UpdateError((r.stderr or r.stdout).strip() or f"git {args[0]} fehlgeschlagen")
    return r.stdout.strip()


def _fetch_status() -> dict:
    # Ohne .git kein git aufrufen – auf Macs ohne Entwicklerwerkzeuge öffnet das sonst einen Installationsdialog
    if not (config.ROOT / ".git").exists():
        return {"supported": False, "available": False,
                "hint": f"Einmal {config.UPDATE_SCRIPT} doppelklicken – danach geht das Update hier per Knopfdruck."}
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != BRANCH:
        return {"supported": False, "available": False, "hint": f"Auf Zweig {branch!r} statt {BRANCH!r}."}
    _git("fetch", "-q", "origin", BRANCH, timeout=60)
    behind = int(_git("rev-list", "--count", f"HEAD..{REMOTE}"))
    ahead = int(_git("rev-list", "--count", f"{REMOTE}..HEAD"))
    commits = _git("log", "--format=%s", f"HEAD..{REMOTE}").splitlines() if behind else []
    return {"supported": True, "available": behind > 0, "behind": behind, "ahead": ahead, "commits": commits[:15]}


def status(force: bool = False) -> dict:
    """Update-Stand, höchstens alle CHECK_EVERY Sekunden frisch von GitHub."""
    with _lock:
        if force or _cache["status"] is None or time.time() - _cache["at"] > CHECK_EVERY:
            try:
                result = _fetch_status()
            except (UpdateError, OSError, subprocess.TimeoutExpired) as e:  # offline o. Ä.: einfach kein Button
                result = {"supported": True, "available": False, "error": str(e)}
            _cache.update(at=time.time(), status=result)
        return {**_cache["status"], "checked_at": _cache["at"], "started": STARTED}


def _python() -> str:
    venv = config.venv_python(config.ROOT)
    return str(venv) if venv.exists() else sys.executable


def apply() -> dict:
    """Neueste Version holen (nur Vorspulen, nie mergen). Liefert, was sich geändert hat."""
    with _lock:
        s = _fetch_status()
        if not s["supported"]:
            raise UpdateError(s["hint"])
        if not s["available"]:
            _cache.update(at=time.time(), status=s)
            return {"updated": False, "commits": []}
        if s["ahead"]:
            raise UpdateError(f"Hier gibt es {s['ahead']} eigene Commits, die nicht auf GitHub sind – "
                              "bitte selbst zusammenführen (git pull).")
        changed = _git("diff", "--name-only", "HEAD", REMOTE).splitlines()
        if "requirements.txt" in changed:
            # Pakete zuerst – sonst startet der Server mit neuem Code, aber ohne die neuen Pakete
            with tempfile.TemporaryDirectory() as tmp:
                req = Path(tmp) / "requirements.txt"
                req.write_text(_git("show", f"{REMOTE}:requirements.txt") + "\n", encoding="utf-8")
                r = subprocess.run([_python(), "-m", "pip", "install", "-q", "-r", str(req)],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
                if r.returncode:
                    raise UpdateError("Neue Pakete konnten nicht installiert werden (Internet?): "
                                      + (r.stderr or r.stdout).strip()[-400:])
        try:
            _git("merge", "--ff-only", "-q", REMOTE)
        except UpdateError as e:
            raise UpdateError(f"Update nicht möglich – vermutlich wurden Dateien der App von Hand geändert. ({e})") from None
        _cache.update(at=0.0, status=None)
        return {
            "updated": True, "commits": s["commits"],
            "reload": any(p.startswith("app/") for p in changed),
            # Der Trainingsapp-Server in Claude (MCP) läuft separat und lädt neuen Code erst nach einem Neustart
            "restart_claude": any(p.startswith("app/") and p.endswith(".py") for p in changed),
        }
