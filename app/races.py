"""B/C-Wettkämpfe: Mini-Taper davor und Erholung danach – abhängig von Distanz und Priorität.

Je länger und belastender der Wettkampf, desto länger die Erholung. Laufen zerstört durch die
exzentrische Belastung am meisten Muskulatur, deshalb gibt es nach langen Läufen zusätzlich eine
Laufpause (Rad/Schwimmen locker statt Laufen).

Phasen nach dem Rennen:
    1 … rest          nur Regeneration (kurz, sehr locker)
    rest+1 … recovery keine harten Einheiten, Umfang steigt von 70 % auf 90 %
    1 … no_run        statt Laufen lockeres Rad (oder nichts, wenn am Tag schon Rad geplant ist)

C-Wettkämpfe werden durchtrainiert und meist nicht voll gelaufen: kürzerer Taper, Erholung ×0,6.
Werte sind Faustregeln – hier anpassen.
"""
from dataclasses import dataclass
from datetime import date
from math import ceil


@dataclass(frozen=True)
class Distance:
    label: str
    taper: int       # Tage Mini-Taper vor einem B-Wettkampf
    rest: int        # Tage nur Regeneration danach
    recovery: int    # Tage ohne harte Einheiten danach (inkl. rest)
    no_run: int = 0  # Tage Laufpause danach


DISTANCES = {
    "run_5k": Distance("Lauf 5 km", taper=2, rest=0, recovery=2),
    "run_10k": Distance("Lauf 10 km", taper=3, rest=1, recovery=3),
    "run_half": Distance("Halbmarathon", taper=4, rest=1, recovery=7, no_run=2),
    "run_marathon": Distance("Marathon", taper=7, rest=3, recovery=14, no_run=5),
    "run_ultra": Distance("Ultralauf (über 42 km)", taper=7, rest=4, recovery=21, no_run=7),
    "tri_sprint": Distance("Triathlon Sprint", taper=2, rest=0, recovery=2),
    "tri_olympic": Distance("Triathlon Olympisch", taper=3, rest=1, recovery=4, no_run=1),
    "half": Distance("Ironman 70.3 (Mitteldistanz)", taper=4, rest=2, recovery=7, no_run=3),
    "ironman": Distance("Ironman (Langdistanz)", taper=10, rest=4, recovery=21, no_run=7),
    "ride": Distance("Radrennen / Zeitfahren", taper=2, rest=1, recovery=3),
    "other": Distance("Anderer Wettkampf", taper=3, rest=1, recovery=3),
}
C_TAPER_MAX = 2        # C-Wettkampf: höchstens 2 Tage locker davor
A_TAPER_CHECK = 3      # A-Rennen: das lange Tapering steuert die Periodisierung, hier nur die letzten Tage
C_RECOVERY_FACTOR = 0.6


def profile(race: dict) -> dict:
    """Tage für Taper/Erholung dieses Wettkampfs (Priorität berücksichtigt)."""
    d = DISTANCES.get(race.get("race_type"), DISTANCES["other"])
    if race.get("priority") == "A":
        return {"taper": min(A_TAPER_CHECK, d.taper), "rest": d.rest, "recovery": d.recovery, "no_run": d.no_run}
    if race.get("priority") == "C":
        scale = lambda days: ceil(days * C_RECOVERY_FACTOR)  # noqa: E731
        return {"taper": min(C_TAPER_MAX, d.taper), "rest": scale(d.rest), "recovery": scale(d.recovery),
                "no_run": scale(d.no_run)}
    return {"taper": d.taper, "rest": d.rest, "recovery": d.recovery, "no_run": d.no_run}


def catalog() -> list[dict]:
    """Für die Oberfläche: alle Distanzen mit Erholungswerten für B und C."""
    return [{"key": k, "label": d.label, "B": profile({"race_type": k, "priority": "B"}),
             "C": profile({"race_type": k, "priority": "C"})} for k, d in DISTANCES.items()]


def effect(day: date, races: list[dict]) -> dict | None:
    """Wirkung eines Wettkampfs auf `day`: race (Renntag) > before (Mini-Taper) > after (Erholung).

    → {"type", "race", "days" (Abstand in Tagen), **profile}
    """
    effects = []
    for r in races:
        diff = (date.fromisoformat(r["date"]) - day).days
        p = profile(r)
        if diff == 0:
            effects.append((0, {"type": "race", "race": r, "days": 0, **p}))
        elif 0 < diff <= p["taper"]:
            effects.append((1, {"type": "before", "race": r, "days": diff, **p}))
        elif 0 < -diff <= max(p["recovery"], p["no_run"]):
            effects.append((2, {"type": "after", "race": r, "days": -diff, **p}))
    return min(effects, key=lambda e: e[0])[1] if effects else None
