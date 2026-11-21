"""Belegte Zeiten aus Kalendern (iCal-Links), damit eine KI Trainingseinheiten in freie Zeitfenster legt.

Jeder gängige Kalender bietet einen iCal-Link (iCloud: Kalender teilen → öffentlicher Kalender; Outlook: Kalender
veröffentlichen → ICS). Gelesen werden nur Beginn und
Ende der Termine, inklusive Wiederholungen (z. B. Vorlesungen). Titel werden bewusst nicht weitergegeben –
in den KI-Auftrag gelangen nur Uhrzeiten. Eintägige Ganztagstermine (Erinnerungen wie Abgaben, Geburtstage) blockieren
nicht; mehrtägige (Reise, Urlaub) gelten als ganztägig belegt.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

LOCAL = ZoneInfo("Europe/Berlin")
MAX_CALENDARS = 5


def _local(value) -> datetime | date:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=LOCAL)).astimezone(LOCAL)
    return value


def busy_from_ics(text: str, first: date, last: date) -> dict[date, list[tuple[str, str] | str]]:
    """Belegte Zeiten je Tag zwischen first und last: [("08:00", "12:00"), …] oder ["ganztägig"]."""
    import icalendar
    import recurring_ical_events

    cal = icalendar.Calendar.from_ical(text)
    events = recurring_ical_events.of(cal).between(first, last + timedelta(days=1))
    days: dict[date, list] = {}
    for ev in events:
        if str(ev.get("TRANSP", "")).upper() == "TRANSPARENT" or str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue  # als „frei“ markierte bzw. abgesagte Termine blockieren nichts
        start, end = _local(ev.decoded("DTSTART")), ev.get("DTEND")
        end = _local(ev.decoded("DTEND")) if end is not None else start
        if not isinstance(start, datetime):  # ganztägig (Ende exklusiv)
            if (end - start).days <= 1:
                continue  # eintägige Ganztagstermine sind fast immer Erinnerungen (Abgabe, Geburtstag) – blockieren nicht
            day = start
            while day < (end if end > start else start + timedelta(days=1)):
                if first <= day <= last:
                    days.setdefault(day, []).append("ganztägig")
                day += timedelta(days=1)
            continue
        day = start.date()
        while day <= end.date():  # über Mitternacht gehende Termine auf die Tage verteilen
            if first <= day <= last:
                a = start if day == start.date() else datetime.combine(day, time(0), LOCAL)
                b = end if day == end.date() else datetime.combine(day, time(23, 59), LOCAL)
                if b > a:
                    days.setdefault(day, []).append((a.strftime("%H:%M"), b.strftime("%H:%M")))
            day += timedelta(days=1)
    return {d: merge(v) for d, v in days.items()}


def merge(slots: list) -> list:
    """Überlappende Zeiten zusammenfassen; ganztägig schlägt alles."""
    if "ganztägig" in slots:
        return ["ganztägig"]
    out: list[list[str]] = []
    for a, b in sorted(slots):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(x) for x in out]


def busy(urls: list[str], first: date, last: date) -> tuple[dict[date, list], list[str]]:
    """Belegte Zeiten aus allen Kalendern zusammen und Fehlermeldungen je Kalender (ohne den Link zu verraten)."""
    combined: dict[date, list] = {}
    errors = []
    for i, url in enumerate([u.strip() for u in urls if u and u.strip()][:MAX_CALENDARS], 1):
        try:
            url = "https://" + url[len("webcal://"):] if url.startswith("webcal://") else url
            r = httpx.get(url, timeout=20, follow_redirects=True)
            r.raise_for_status()
            for day, slots in busy_from_ics(r.text, first, last).items():
                combined.setdefault(day, []).extend(slots)
        except Exception as e:  # noqa: BLE001 – ein kaputter Kalender soll den Auftrag nicht verhindern
            errors.append(f"Kalender {i} nicht lesbar ({type(e).__name__})")
    return {d: merge(v) for d, v in sorted(combined.items())}, errors
