"""Google Kalender: geplante Workouts als ganztägige Termine in einen Kalender (Standard: "Sport") schreiben.

Einrichtung (einmalig, siehe README „Google Kalender“):
1. Google Cloud Console: Projekt, Google Calendar API aktivieren, OAuth-Client "Desktop-App" anlegen,
   JSON herunterladen nach ~/.trainingsapp/google_client_secret.json
2. Anmelden:  .venv/bin/python -m app.google_login
Danach wie Garmin/Wahoo/Zwift: Häkchen „Google Kalender“ beim Speichern oder Auto-Sync in den Einstellungen.
"""
from datetime import date, timedelta

import httpx

from .. import config
from ..workouts import total_duration

API = "https://www.googleapis.com/calendar/v3"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",                # Termine anlegen/ändern/löschen
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",  # Kalender "Sport" per Name finden
]
SPORT_DE = {"swim": "Schwimmen", "ride": "Radfahren", "run": "Laufen", "strength": "Stabi / Kraft",
            "mobility": "Dehnen / Yoga", "other": "Sonstiges"}
MAX_TITLE_NAME = 30  # längere Programmnamen stehen nur in der Beschreibung
KIND_DE = {"warmup": "Einwärmen", "interval": "Intervall", "recovery": "Erholung", "steady": "Konstant",
           "cooldown": "Ausfahren"}
_calendar_ids: dict[str, str] = {}


def is_connected() -> bool:
    return config.GOOGLE_SERVICE_ACCOUNT_FILE.exists() or config.GOOGLE_TOKEN_FILE.exists()


def _token() -> str:
    """Gültiges Access-Token (wird bei Bedarf mit dem Refresh-Token erneuert und gespeichert)."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials

    if config.GOOGLE_SERVICE_ACCOUNT_FILE.exists():
        creds = ServiceAccountCredentials.from_service_account_file(str(config.GOOGLE_SERVICE_ACCOUNT_FILE), scopes=SCOPES[:1])
        creds.refresh(Request())
        return creds.token
    if not is_connected():
        raise RuntimeError("Nicht bei Google angemeldet. Im Terminal ausführen: .venv/bin/python -m app.google_login")
    creds = Credentials.from_authorized_user_file(str(config.GOOGLE_TOKEN_FILE), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError:
            raise RuntimeError("Google-Anmeldung abgelaufen. Neu anmelden: .venv/bin/python -m app.google_login") from None
        config.GOOGLE_TOKEN_FILE.write_text(creds.to_json())
    return creds.token


def _http() -> httpx.Client:
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {_token()}"}, timeout=20)


def calendar_id(h: httpx.Client, name: str) -> str:
    """ID des Kalenders mit diesem Namen (z. B. "Sport"). Eine Kalender-ID (mit @) gilt direkt – das Dienstkonto sieht keine Namen."""
    if "@" in name:
        return name
    if name not in _calendar_ids:
        r = h.get("/users/me/calendarList", params={"maxResults": 250})
        r.raise_for_status()
        for c in r.json().get("items", []):
            _calendar_ids[c.get("summary", "")] = c["id"]
        if name not in _calendar_ids:
            raise RuntimeError(f"Kalender „{name}“ nicht gefunden. Name in den Einstellungen prüfen.")
    return _calendar_ids[name]


def _pace(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"


def target_text(workout: dict, step: dict, settings: dict) -> str:
    """Zielbereich eines Schritts in Watt / Pace / Puls – wie die Anzeige im Editor."""
    low, high = float(step.get("low") or 0), float(step.get("high") or step.get("low") or 0)
    sport, target = workout.get("sport"), workout.get("target", "power")
    if not (low or high) or sport in ("strength", "mobility"):
        return ""
    if target == "power":
        lo, hi, unit = round(settings["ftp"] * low / 100), round(settings["ftp"] * high / 100), " W"
    elif target == "hr":
        lthr = settings["lthr_ride"] if sport == "ride" else settings["lthr_run"]
        lo, hi, unit = round(lthr * low / 100), round(lthr * high / 100), " bpm"
    else:  # mehr % = schneller
        base = settings["css"] if sport == "swim" else settings["threshold_pace"]
        lo, hi = _pace(base / (low / 100)), _pace(base / (high / 100))
        unit = " /100 m" if sport == "swim" else " /km"
    return f"{lo}{unit}" if lo == hi else f"{lo}–{hi}{unit}"


def _step_lines(workout: dict, steps: list[dict], settings: dict, indent: str = "") -> list[str]:
    lines = []
    for s in steps:
        if s.get("kind") == "repeat":
            lines.append(f"{indent}{s['count']}×")
            lines += _step_lines(workout, s.get("steps", []), settings, indent + "   ")
        else:
            minutes = s["duration"] / 60
            duration = f"{minutes:g} min" if minutes >= 1 else f"{s['duration']} s"
            target = target_text(workout, s, settings)
            lines.append(f"{indent}• {duration} {KIND_DE.get(s['kind'], s['kind'])}" + (f" – {target}" if target else ""))
    return lines


def _short_name(name: str) -> str:
    """Programm für den Titel: ohne Klammerzusatz, wenn nötig nur der Teil vor dem Doppelpunkt; zu lang → leer."""
    short = name.split(" (")[0].strip()
    if len(short) > MAX_TITLE_NAME:
        short = short.split(": ")[0]
    return short if len(short) <= MAX_TITLE_NAME else ""


def event_body(workout: dict, settings: dict) -> dict:
    """Ganztägiger Termin: Titel „Sportart – Programm“; Beschreibung mit vollem Namen, Schritten in absoluten Werten, Dauer und TSS."""
    from ..workouts import estimate_tss

    minutes = round(total_duration(workout.get("steps", [])) / 60)
    duration = f"{minutes // 60}:{minutes % 60:02d} h" if minutes >= 60 else f"{minutes} min"
    day = date.fromisoformat(workout["date"])
    sport = SPORT_DE.get(workout.get("sport"), SPORT_DE["other"])
    name = workout.get("name", "Workout")
    short = _short_name(name)
    description = "\n".join(filter(None, [
        name if short != name else "",  # im Titel gekürzt → hier vollständig
        workout.get("description", ""),
        "",
        *_step_lines(workout, workout.get("steps", []), settings),
        "",
        f"Geplant mit der Trainingsapp · {duration} · {round(estimate_tss(workout))} TSS",
    ])).strip()
    return {
        "summary": f"{sport} – {short}" if short and short != sport else sport,
        "description": description,
        "start": {"date": day.isoformat()},
        "end": {"date": (day + timedelta(days=1)).isoformat()},
        "transparency": "transparent",  # blockiert keine Zeit („verfügbar“)
        "extendedProperties": {"private": {"trainingsapp_id": str(workout.get("id", ""))}},
    }


def push(workout: dict, settings: dict) -> dict:
    existing = (workout.get("sync") or {}).get("google") or {}
    body = event_body(workout, settings)
    with _http() as h:
        cal = calendar_id(h, settings.get("google_calendar") or "Sport")
        if existing.get("event_id") and existing.get("calendar_id") == cal:
            r = h.put(f"/calendars/{cal}/events/{existing['event_id']}", json=body)
            if r.status_code not in (404, 410):
                r.raise_for_status()
                return {"event_id": r.json()["id"], "calendar_id": cal}
        elif existing.get("event_id"):  # Kalender gewechselt → alten Termin entfernen
            h.delete(f"/calendars/{existing['calendar_id']}/events/{existing['event_id']}")
        r = h.post(f"/calendars/{cal}/events", json=body)
        r.raise_for_status()
        return {"event_id": r.json()["id"], "calendar_id": cal}


def remove(workout: dict) -> None:
    info = (workout.get("sync") or {}).get("google") or {}
    if info.get("event_id") and is_connected():
        with _http() as h:
            r = h.delete(f"/calendars/{info['calendar_id']}/events/{info['event_id']}")
            if r.status_code not in (200, 204, 404, 410):  # schon gelöscht ist ok
                r.raise_for_status()
