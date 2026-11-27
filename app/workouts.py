"""Workout-Struktur und Kennzahlen.

Ein Workout ist ein dict:
    {
      "date": "2026-10-25",
      "sport": "swim" | "ride" | "run" | "strength" (Stabi/Kraft) | "mobility" (Dehnen/Yoga) | "other",
      "name": "...", "description": "...",
      "target": "power" | "pace" | "hr",   # % von FTP / Schwellentempo bzw. CSS / LTHR des Sports
      "steps": [ Schritt, ... ],
      "status": "planned" | "done", "actual_tss": None,
      "sync": {"garmin": {...}, "intervals": {...}, "zwift": {...}}
    }

Ein Schritt:
    {"kind": "warmup" | "interval" | "recovery" | "steady" | "cooldown",
     "duration": Sekunden, "low": %, "high": %,
     "target": "power" | "pace" | "hr"}       # optional: weicht vom Ziel des Workouts ab (z. B. Einlaufen nach Puls)
oder eine Wiederholung:
    {"kind": "repeat", "count": 5, "steps": [Schritt, ...]}
"""
import re
from collections.abc import Iterator

STEP_KINDS = ("warmup", "interval", "recovery", "steady", "cooldown")
SPORTS = ("swim", "ride", "run", "strength", "mobility", "other")
# Ohne Intensitätsziel: TSS pauschal pro Stunde
FLAT_TSS_PER_HOUR = {"strength": 40, "mobility": 10}
TARGETS = ("power", "pace", "hr")


def step_target(workout: dict, s: dict) -> str:
    """Ziel eines Schritts: eigenes "target" des Schritts, sonst das des Workouts."""
    return s.get("target") if s.get("target") in TARGETS else workout.get("target", "power")


def step(kind: str, minutes: float, low: float, high: float | None = None) -> dict:
    return {"kind": kind, "duration": int(round(minutes * 60)), "low": low, "high": high if high is not None else low}


def repeat(count: int, *steps: dict) -> dict:
    return {"kind": "repeat", "count": count, "steps": list(steps)}


def flatten(steps: list[dict]) -> Iterator[dict]:
    """Alle Einzelschritte in Ausführungsreihenfolge (Wiederholungen ausgerollt)."""
    for s in steps:
        if s.get("kind") == "repeat":
            for _ in range(int(s.get("count", 1))):
                yield from flatten(s.get("steps", []))
        else:
            yield s


def total_duration(steps: list[dict]) -> int:
    return sum(int(s.get("duration", 0)) for s in flatten(steps))


def estimate_tss(workout: dict) -> float:
    """TSS ≈ Σ Stunden × IF² × 100, IF = mittlere Zielintensität des Schritts."""
    if workout.get("sport") in FLAT_TSS_PER_HOUR:
        return round(total_duration(workout.get("steps", [])) / 3600 * FLAT_TSS_PER_HOUR[workout["sport"]], 1)
    tss = 0.0
    for s in flatten(workout.get("steps", [])):
        intensity = (float(s.get("low", 0)) + float(s.get("high", s.get("low", 0)))) / 200
        tss += s.get("duration", 0) / 3600 * intensity**2 * 100
    return round(tss, 1)


def intensity_factor(workout: dict) -> float:
    hours = total_duration(workout.get("steps", [])) / 3600
    return round((estimate_tss(workout) / (hours * 100)) ** 0.5, 2) if hours else 0.0


# „8 km“, „8–10 km“, „9,5 km“, „3200 m“ im Namen – nicht „5×400 m“ (Teilstrecke einer Wiederholung)
DISTANCE_IN_NAME = re.compile(r"(?<![\dx×.,])\s?(\d+(?:[.,]\d+)?)(?:\s*[–-]\s*(\d+(?:[.,]\d+)?))?\s*(km|m)\b", re.I)
PACE_BASE = {"run": ("threshold_pace", 1000), "swim": ("css", 100)}  # Schwelle in s pro km bzw. 100 m


def distance_from_name(name: str | None) -> float | None:
    """Meter aus dem Namen, bei Spannen die Mitte („8–10 km“ → 9000)."""
    m = DISTANCE_IN_NAME.search(name or "")
    if not m:
        return None
    low = float(m[1].replace(",", "."))
    high = float(m[2].replace(",", ".")) if m[2] else low
    return (low + high) / 2 * (1000 if m[3].lower() == "km" else 1)


def estimate_distance(workout: dict, settings: dict) -> float:
    """Geplante Strecke in Metern (0 = unbekannt). Zuerst aus dem Namen, sonst aus den Schritten:
    Tempo = Schwelle / Intensität. Puls- und Wattziele werden dabei wie Tempo-Prozente behandelt (grobe Schätzung)."""
    from_name = distance_from_name(workout.get("name"))
    if from_name:
        return from_name
    key, unit = PACE_BASE.get(workout.get("sport"), (None, 0))
    threshold = float(settings.get(key) or 0) if key else 0
    if not threshold:
        return 0.0
    meters = 0.0
    for s in flatten(workout.get("steps", [])):
        pct = (float(s.get("low", 0)) + float(s.get("high", s.get("low", 0)))) / 2
        if pct > 0:  # 0 % = Pause am Beckenrand
            meters += s.get("duration", 0) / (threshold / (pct / 100)) * unit
    return round(meters)


def summarize(workout: dict) -> dict:
    """Workout um berechnete Felder ergänzen (für API-Antworten)."""
    return {
        **workout,
        "duration": total_duration(workout.get("steps", [])),
        "tss": estimate_tss(workout),
        "if": intensity_factor(workout),
    }


def fmt_duration(seconds: int) -> str:
    """Dauer im Stil von intervals.icu: 1h20m, 4m30s, 45s."""
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    out = ""
    if h:
        out += f"{h}h"
    if m:
        out += f"{m}m"
    if s or not out:
        out += f"{s}s"
    return out
