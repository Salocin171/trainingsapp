"""Ziele für die Workout-Übertragung. Neues Ziel = Modul mit push()/remove() + Eintrag hier."""
from . import garmin, google_calendar, intervals, zwift

TARGETS = {
    "garmin": garmin,       # → Garmin-Uhr / -Radcomputer (über Garmin-Connect-Kalender)
    "intervals": intervals, # → Wahoo (über intervals.icu)
    "zwift": zwift,         # → Zwift (lokale .zwo-Datei)
    "google": google_calendar,  # → Google Kalender (z. B. Kalender „Sport“)
}


# Sportarten, die ein Ziel versteht (fehlt der Eintrag: alle)
SUPPORTED_SPORTS = {"zwift": {"ride", "run"}}


def supports(target: str, sport: str) -> bool:
    return sport in SUPPORTED_SPORTS.get(target, {sport})


def status() -> dict:
    zwift_ok = True
    try:
        zwift.workouts_dir()
    except RuntimeError:
        zwift_ok = False
    return {"garmin": garmin.is_connected(), "intervals": intervals.is_connected(), "zwift": zwift_ok,
            "google": google_calendar.is_connected()}
