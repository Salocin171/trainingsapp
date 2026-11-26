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
