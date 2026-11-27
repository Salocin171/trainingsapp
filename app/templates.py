"""Workout-Vorlagen. Jede Vorlage baut Schritte für eine Gesamtdauer in Minuten.

Intensitäten in % von FTP (Rad), % der Schwellengeschwindigkeit (Lauf) bzw. % der
CSS-Geschwindigkeit (Schwimmen). Kraft/Stabi und Dehnen/Yoga haben kein Intensitätsziel (0 %).
Eigene Vorlagen: Funktion schreiben und in TEMPLATES eintragen.
"""
from typing import Callable, NamedTuple

from .workouts import estimate_tss, intensity_factor, repeat, step

ENDURANCE_SPORTS = ("swim", "ride", "run")

ZONES = {
    "ride": {"rec": (45, 55), "endu": (65, 75), "race": (70, 76), "tempo": (82, 88), "ss": (88, 93),
             "thr": (97, 102), "vo2": (110, 118), "open": (115, 125), "off": (50, 55)},
    "run": {"rec": (65, 72), "endu": (72, 82), "race": (82, 87), "tempo": (86, 91), "ss": (90, 94),
            "thr": (97, 101), "vo2": (104, 110), "open": (108, 115), "off": (65, 70)},
    # Pause beim Schwimmen = stehen am Beckenrand → kein Ziel
    "swim": {"rec": (70, 78), "endu": (80, 88), "race": (88, 92), "tempo": (90, 94), "ss": (94, 97),
             "thr": (98, 102), "vo2": (103, 108), "open": (100, 105), "off": (0, 0)},
}
# Intervalle je Sport: (Belastung min, Pause min, min. Wiederholungen, max. Wiederholungen)
INTERVALS = {
    "tempo": {"ride": (15, 5, 2, 4), "run": (12, 3, 2, 4), "swim": (6, 0.5, 3, 8)},
    "sweetspot": {"ride": (12, 5, 2, 5), "run": (10, 3, 2, 5), "swim": (5, 0.5, 3, 8)},
    "threshold": {"ride": (8, 4, 3, 6), "run": (6, 2, 3, 6), "swim": (4, 0.5, 4, 10)},
    "vo2max": {"ride": (4, 4, 4, 7), "run": (3, 3, 4, 7), "swim": (1.5, 0.75, 6, 12)},
    "openers": {"ride": (1, 3, 3, 4), "run": (1, 2, 3, 4), "swim": (0.75, 0.75, 4, 6)},
    "race_pace": {"ride": (30, 5, 2, 5), "run": (15, 3, 2, 4), "swim": (8, 0.5, 2, 5)},
}


def _z(sport: str, name: str) -> tuple[float, float]:
    return ZONES[sport if sport in ZONES else "ride"][name]


def _warm_cool(sport: str) -> tuple[int, int]:
    return (10, 5) if sport == "swim" else (15, 10)


def _with_intervals(kind: str, zone: str):
    """Einwärmen, n × (Belastung/Pause), Rest locker auffüllen, Ausfahren."""
    def build(sport: str, minutes: int) -> list[dict]:
        on, off, n_min, n_max = INTERVALS[kind][sport if sport in ENDURANCE_SPORTS else "ride"]
        warm, cool = _warm_cool(sport)
        budget = minutes - warm - cool
        n = max(n_min, min(n_max, int(budget // (on + off))))
        fill = max(0, budget - n * (on + off))
        steps = [step("warmup", warm, _z(sport, "rec")[0], _z(sport, "endu")[1]),
                 repeat(n, step("interval", on, *_z(sport, zone)), step("recovery", off, *_z(sport, "off")))]
        if fill >= 5:
            steps.append(step("steady", fill, *_z(sport, "endu")))
        steps.append(step("cooldown", cool, _z(sport, "rec")[0], _z(sport, "endu")[0]))
        return steps
    return build


def recovery(sport, minutes):
    return [step("steady", minutes, *_z(sport, "rec"))]


def endurance(sport, minutes):
    warm, cool = _warm_cool(sport)
    return [step("warmup", warm, _z(sport, "rec")[0], _z(sport, "endu")[0]),
            step("steady", max(5, minutes - warm - cool), *_z(sport, "endu")),
            step("cooldown", cool, _z(sport, "rec")[0], _z(sport, "endu")[0])]


def brick(sport, minutes):
    """Koppellauf direkt nach dem Rad: kurz einlaufen, dann Wettkampftempo."""
    return [step("warmup", 5, *_z("run", "endu")), step("steady", max(5, minutes - 5), *_z("run", "race"))]


# Zirkel-Timer (Kraft/Stabi): Belastung/Pause je Übung, Pause nach jeder Runde (Sekunden)
STABI_EXERCISES = ["Plank", "Seitstütz", "Glute Bridge einbeinig", "Dead Bug", "Bird Dog", "Ausfallschritte",
                   "Wadenheben", "Kniebeugen einbeinig", "Rudern mit Band"]
STABI_CIRCUIT = {"work": 40, "rest": 20, "round_rest": 120}


def stabi_circuit(steps: list[dict]) -> dict:
    """Timer-Einstellungen passend zu den Stabi-Schritten: eine Runde je Wiederholung."""
    rounds = next((s["count"] for s in steps if s.get("kind") == "repeat"), 1)
    return {**STABI_CIRCUIT, "rounds": rounds, "exercises": list(STABI_EXERCISES)}


def circuit_exercises(circuit: dict) -> list[dict]:
    """Übungen als {"name", "reps"?, "seconds"?} – ältere Zirkel speichern nur Namen (= Zeit wie "work")."""
    return [{"name": e} if isinstance(e, str) else e for e in circuit.get("exercises") or []]


def circuit_for(workout: dict) -> dict | None:
    """Gespeicherter Zirkel oder – bei Stabi-Workouts von der Vorlage – der Standard-Zirkel."""
    if workout.get("circuit"):
        return workout["circuit"]
    return stabi_circuit(workout.get("steps", [])) if workout.get("template") == "stabi" else None


def stabi(sport, minutes):
    rounds = max(1, round((minutes - 10) / 12))
    return [step("warmup", 5, 0), repeat(rounds, step("interval", 10, 0), step("recovery", 2, 0)),
            step("cooldown", 5, 0)]


def mobility(sport, minutes):
    return [step("steady", minutes, 0)]


class Template(NamedTuple):
    name: str
    build: Callable[[str, int], list[dict]]
    min: int
    max: int
    hard: bool
    sports: tuple[str, ...]


TEMPLATES = {
    "recovery": Template("Regeneration", recovery, 20, 60, False, ENDURANCE_SPORTS),
    "endurance": Template("Grundlage", endurance, 30, 180, False, ENDURANCE_SPORTS),
    "long": Template("Lange Grundlage", endurance, 60, 360, False, ENDURANCE_SPORTS),
    "race_pace": Template("Wettkampftempo", _with_intervals("race_pace", "race"), 45, 300, False, ENDURANCE_SPORTS),
    "tempo": Template("Tempo", _with_intervals("tempo", "tempo"), 40, 100, True, ENDURANCE_SPORTS),
    "sweetspot": Template("Sweet Spot", _with_intervals("sweetspot", "ss"), 40, 110, True, ENDURANCE_SPORTS),
    "threshold": Template("Schwelle", _with_intervals("threshold", "thr"), 40, 100, True, ENDURANCE_SPORTS),
    "vo2max": Template("VO2max", _with_intervals("vo2max", "vo2"), 40, 90, True, ENDURANCE_SPORTS),
    "openers": Template("Aktivierung", _with_intervals("openers", "open"), 20, 50, False, ENDURANCE_SPORTS),
    "brick": Template("Koppellauf", brick, 10, 60, False, ("run",)),
    "stabi": Template("Stabi / Kraft", stabi, 20, 70, False, ("strength",)),
    "mobility": Template("Dehnen / Yoga", mobility, 10, 75, False, ("mobility",)),
}

# Sinnvolle Dauer je Sport (überschreibt min/max der Vorlage)
SPORT_LIMITS = {
    ("endurance", "swim"): (30, 75), ("endurance", "run"): (30, 100),
    ("long", "swim"): (45, 90), ("long", "run"): (60, 150), ("long", "ride"): (90, 360),
    ("race_pace", "swim"): (40, 75), ("race_pace", "run"): (45, 120), ("race_pace", "ride"): (90, 300),
}

DESCRIPTIONS = {
    "recovery": "Ganz locker, Beine durchbewegen. Puls niedrig halten.",
    "endurance": "Ruhige Grundlage, Gesprächstempo.",
    "long": "Lange, gleichmäßige Grundlage. Verpflegung nicht vergessen.",
    "race_pace": "Blöcke im geplanten Wettkampftempo. Verpflegung und Material wie im Rennen.",
    "tempo": "Zügig, aber kontrolliert. Gleichmäßige Intervalle.",
    "sweetspot": "Knapp unter der Schwelle – viel Trainingsreiz bei moderater Ermüdung.",
    "threshold": "An der Schwelle. Letztes Intervall soll hart, aber machbar sein.",
    "vo2max": "Kurze, harte Intervalle zur Steigerung der maximalen Sauerstoffaufnahme.",
    "openers": "Kurze Spitzen zum Aktivieren vor einem Wettkampf.",
    "brick": "Direkt nach dem Rad loslaufen. Ziel: schnell ins Wettkampftempo finden.",
    "stabi": f"Zirkel, {STABI_CIRCUIT['work']} s Belastung / {STABI_CIRCUIT['rest']} s Pause je Übung: "
             f"{', '.join(STABI_EXERCISES)}.",
    "mobility": "Dehnen / Yoga: Hüftbeuger, Hamstrings, Waden, Brustwirbelsäule, Schultern. "
                "Ruhig atmen, nichts erzwingen.",
}
SWIM_HINT = " Pausen am Beckenrand. Ziel in % der CSS-Geschwindigkeit."


def limits(kind: str, sport: str) -> tuple[int, int]:
    t = TEMPLATES[kind]
    return SPORT_LIMITS.get((kind, sport), (t.min, t.max))


def default_target(sport: str) -> str:
    return {"ride": "power", "run": "pace", "swim": "pace"}.get(sport, "hr")


def build(kind: str, sport: str, minutes: int) -> dict:
    t = TEMPLATES[kind]
    if sport not in t.sports:
        sport = t.sports[0]
    lo, hi = limits(kind, sport)
    minutes = max(lo, min(hi, int(minutes)))
    description = DESCRIPTIONS[kind] + (SWIM_HINT if sport == "swim" else "")
    workout = {
        "sport": sport,
        "name": t.name,
        "description": description,
        "target": default_target(sport),
        "template": kind,
        "steps": t.build(sport, minutes),
    }
    if kind == "stabi":
        workout["circuit"] = stabi_circuit(workout["steps"])
    return workout


def build_for_tss(kind: str, sport: str, target_tss: float) -> dict:
    """Dauer so wählen, dass der geschätzte TSS dem Ziel am nächsten kommt."""
    lo, hi = limits(kind, sport)
    best = min(range(lo, hi + 1, 5), key=lambda m: abs(estimate_tss(build(kind, sport, m)) - target_tss))
    return build(kind, sport, best)


def is_hard(kind: str) -> bool:
    t = TEMPLATES.get(kind)
    return bool(t and t.hard)


def is_hard_workout(w: dict) -> bool:
    """Hart = harte Vorlage oder Intensitätsfaktor ab 0,85."""
    return is_hard(w.get("template", "")) or intensity_factor(w) >= 0.85
