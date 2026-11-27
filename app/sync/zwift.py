"""Zwift: Workouts als .zwo-Datei in den lokalen Zwift-Ordner schreiben.

Zwift liest beim Start alle Dateien aus ~/Documents/Zwift/Workouts/<Zwift-ID>/
(Windows: oft unter OneDrive umgeleitet) und zeigt sie unter "Custom Workouts". Einen Kalender hat Zwift dafür nicht,
deshalb steht das Datum vorne im Dateinamen.
"""
import re
from pathlib import Path
from xml.sax.saxutils import quoteattr, escape

from ..workouts import flatten

def zwift_roots(home: Path | None = None) -> list[Path]:
    """Mögliche Zwift-Workout-Ordner: Dokumente lokal oder (Windows) per OneDrive umgeleitet, auch „Dokumente“."""
    home = home or Path.home()
    docs = [home / "Documents"]
    for onedrive in sorted(home.glob("OneDrive*")):  # „OneDrive“ bzw. „OneDrive - Firma“
        docs += [onedrive / "Documents", onedrive / "Dokumente"]
    return [d / "Zwift" / "Workouts" for d in docs]


def workouts_dir(configured: str = "", home: Path | None = None) -> Path:
    if configured:
        return Path(configured).expanduser()
    for root in zwift_roots(home):
        if root.is_dir():
            ids = sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit())
            if ids:
                return ids[0]
    raise RuntimeError("Zwift-Workout-Ordner nicht gefunden. Bitte in den Einstellungen setzen.")


def _pct(value: float) -> str:
    return f"{float(value) / 100:.3f}"


def _segment(s: dict) -> str:
    dur = int(s["duration"])
    low, high = s.get("low", 0), s.get("high", s.get("low", 0))
    if s["kind"] == "warmup":
        return f'<Warmup Duration="{dur}" PowerLow="{_pct(low)}" PowerHigh="{_pct(high)}"/>'
    if s["kind"] == "cooldown":
        # Abwärmen läuft von hoch nach niedrig
        return f'<Cooldown Duration="{dur}" PowerLow="{_pct(high)}" PowerHigh="{_pct(low)}"/>'
    return f'<SteadyState Duration="{dur}" Power="{_pct((low + high) / 2)}"/>'


def _segments(steps: list[dict]) -> list[str]:
    out = []
    for s in steps:
        children = s.get("steps", [])
        if s.get("kind") == "repeat" and len(children) == 2 and not any(c.get("kind") == "repeat" for c in children):
            on, off = children
            out.append(
                f'<IntervalsT Repeat="{int(s["count"])}" OnDuration="{int(on["duration"])}" '
                f'OffDuration="{int(off["duration"])}" '
                f'OnPower="{_pct((on["low"] + on["high"]) / 2)}" OffPower="{_pct((off["low"] + off["high"]) / 2)}"/>'
            )
        elif s.get("kind") == "repeat":
            out.extend(_segment(c) for c in flatten([s]))
        else:
            out.append(_segment(s))
    return out


def to_zwo(workout: dict) -> str:
    sport = "run" if workout.get("sport") == "run" else "bike"
    body = "\n        ".join(_segments(workout.get("steps", [])))
    return f"""<workout_file>
    <author>Trainingsapp</author>
    <name>{escape(workout.get("date", "") + " " + workout.get("name", "Workout"))}</name>
    <description>{escape(workout.get("description", ""))}</description>
    <sportType>{sport}</sportType>
    <tags><tag name={quoteattr("Trainingsapp")}/></tags>
    <workout>
        {body}
    </workout>
</workout_file>
"""


def _filename(workout: dict) -> str:
    slug = re.sub(r"[^A-Za-z0-9äöüÄÖÜß_-]+", "_", workout.get("name", "workout")).strip("_")
    return f"{workout['date']}_{slug}_{workout.get('id', 'neu')}.zwo"


def push(workout: dict, settings: dict) -> dict:
    if workout.get("sport") not in ("ride", "run"):
        raise RuntimeError("Zwift unterstützt nur Rad- und Lauf-Workouts.")
    # Hinweis: Beim Laufen interpretiert Zwift die Prozentwerte als % des Schwellentempos.
    remove(workout)
    target = workouts_dir(settings.get("zwift_dir", "")) / _filename(workout)
    target.write_text(to_zwo(workout), encoding="utf-8")
    return {"path": str(target)}


def remove(workout: dict) -> None:
    path = (workout.get("sync") or {}).get("zwift", {}).get("path")
    if path and Path(path).exists():
        Path(path).unlink()
