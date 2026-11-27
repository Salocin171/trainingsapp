"""Abläufe, die Datenbank, Fachlogik und Übertragung an Geräte verbinden.

Schichten der App:
    routes/    HTTP: Eingaben prüfen (schemas.py), Statuscodes, Antworten
    services   dieses Modul: holt Daten aus db, ruft die Fachmodule auf, sendet an sync/
    Fachmodule reine Funktionen ohne Datenbank (compliance, recommend, periodization, volume, nutrition …)
    db / sync  Speicher (SQLite) bzw. Anbindungen (Garmin, intervals.icu, Zwift, Kalender)

Services kennen kein HTTP. Erwartbare Fehler werfen sie als ServiceError (→ 400) oder ExternalError (→ 502).
"""
from datetime import date, datetime, timedelta

from . import (analysis, availability, compliance, conflicts, db, feedback, nutrition, periodization, plan_import,
               plan_prompt, recommend, volume)
from .load import compute_series, daily_tss
from .sync import TARGETS, supports
from .sync import status as sync_status
from .workouts import estimate_tss, summarize

GARMIN_METRICS_MAX_AGE = timedelta(hours=6)
HISTORY_DAYS = 180  # so weit zurück zählen Aktivitäten für CTL/ATL


class ServiceError(Exception):
    """Ungültige Anfrage, z. B. unbekanntes Ziel oder fehlerhafter Plan."""


class ExternalError(Exception):
    """Ein externer Dienst (Garmin, intervals.icu, Kalender-App) hat nicht wie erwartet geantwortet."""


def connected(settings: dict | None = None) -> dict:
    return sync_status(settings or db.get_settings())


# --- Workouts speichern, übertragen, löschen ---------------------------------

def sync_workout(workout: dict, targets: list[str], settings: dict | None = None) -> dict:
    """An die gewünschten Ziele senden. Fehler pro Ziel sammeln statt abzubrechen."""
    settings = settings or db.get_settings()
    sync = dict(workout.get("sync") or {})
    errors = {}
    for name in targets:
        try:
            sync[name] = TARGETS[name].push(workout, settings)
        except Exception as e:  # noqa: BLE001 – Fehlermeldung geht an die Oberfläche
            errors[name] = str(e)
    saved = db.save_workout({**workout, "sync": sync})
    return {"workout": summarize(saved), "errors": errors}


def store_workout(data: dict, settings: dict | None = None) -> dict:
    """Workout speichern. Bereits übertragene Ziele aktuell halten, sonst Auto-Sync – nur wo der Sport passt
    und das Ziel eingerichtet ist (sonst käme bei jedem Speichern ein Fehler, z. B. ohne intervals.icu-Schlüssel)."""
    settings = settings or db.get_settings()
    workout = db.save_workout(data)
    ready = connected(settings)
    auto = {t for t in settings["auto_sync"] if supports(t, workout.get("sport")) and ready.get(t)}
    targets = sorted(set((workout.get("sync") or {}).keys()) | auto)
    if workout.get("status") == "done" or not targets:
        return {"workout": summarize(workout), "errors": {}}
    return sync_workout(workout, targets, settings)


def remove_workout(workout: dict) -> dict:
    """Workout löschen, auch auf den Geräten. Liefert Fehler pro Ziel."""
    errors = {}
    for name in (workout.get("sync") or {}):
        try:
            TARGETS[name].remove(workout)
        except Exception as e:  # noqa: BLE001
            errors[name] = str(e)
    db.delete_workout(workout["id"])
    return errors


def bulk_sync(target: str, days: int, resend: bool) -> dict:
    """Alle geplanten, noch nicht übertragenen Workouts ab heute an ein Ziel senden (z. B. nach der Einrichtung)."""
    if target not in TARGETS:
        raise ServiceError(f"Unbekanntes Ziel: {target}")
    today = date.today()
    settings = db.get_settings()
    pending = [w for w in db.list_workouts(today.isoformat(), (today + timedelta(days=days)).isoformat())
               if w.get("status") != "done" and (resend or target not in (w.get("sync") or {}))
               and supports(target, w.get("sport"))]
    errors = []
    for w in pending:
        errors += [f"{w['date']} {w['name']}: {e}" for e in sync_workout(w, [target], settings)["errors"].values()]
    return {"sent": len(pending) - len(errors), "errors": errors}


def workout_details(workout: dict) -> dict:
    return {**summarize(workout), "nutrition": nutrition.for_workout(workout, db.get_settings(), db.list_workouts)}


def nutrition_plan(workout: dict) -> dict:
    return nutrition.for_workout(workout, db.get_settings(), db.list_workouts)


# --- Kalender ----------------------------------------------------------------

def calendar(start: str, end: str) -> dict:
    """Workouts mit Compliance und Konflikten, Aktivitäten mit Zuordnung, Wettkämpfe und Wocheninfo (Blöcke)."""
    today = date.today()
    settings = db.get_settings()
    b_c_races = db.list_races()
    workouts = db.list_workouts(start, end)
    activities = db.list_activities(start, end)
    rating, unplanned, links = compliance.evaluate(workouts, activities, today, settings)
    clash = {c["workout_id"]: c for c in conflicts.check(workouts, conflicts.race_list(settings, b_c_races), today)}
    races = [{"name": settings["goal_name"] or "Wettkampf", "date": settings["goal_date"], "priority": "A"}] \
        if settings.get("goal_date") else []
    races += b_c_races
    return {
        "workouts": [{**summarize(w), "compliance": rating.get(w["id"]),
                      "conflict": {k: clash[w["id"]][k] for k in ("phase", "problem", "race")} if w["id"] in clash else None}
                     for w in workouts],
        "activities": [{**a, "unplanned": a["id"] in unplanned, "plan": links.get(a["id"])} for a in activities],
        "races": [r for r in races if start <= r["date"] <= end],
        "weeks": periodization.calendar_weeks(settings, date.fromisoformat(start),
                                              date.fromisoformat(end) - timedelta(days=1)),
    }


def save_activity_feedback(activity_id: str, values: dict) -> None:
    """RPE / Befinden / Notiz speichern; eine Zuordnung zum Plan (plan_link) bleibt erhalten."""
    link = {k: v for k, v in db.get_feedback(activity_id).items() if k == "plan_link"}
    db.save_feedback(activity_id, link | {k: v for k, v in values.items() if v not in (None, "")})


def link_activity(activity_id: str, workout_id: int | None) -> None:
    """Zuordnung Aktivität ↔ Workout von Hand: None = automatisch, 0 = gehört zu keinem Workout."""
    data = {k: v for k, v in db.get_feedback(activity_id).items() if k != "plan_link"}
    db.save_feedback(activity_id, data if workout_id is None else {**data, "plan_link": workout_id})


# --- Belastung & Empfehlungen ------------------------------------------------

def load_context(today: date) -> tuple[list[dict], dict[str, float]]:
    """Aktivitäten der letzten Monate und TSS pro Tag (inkl. von Hand als erledigt markierter Workouts)."""
    history_start = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    activities = db.list_activities(history_start, today.isoformat())
    tss = daily_tss(activities, db.list_workouts(history_start, today.isoformat()))
    return activities, tss


def _ctl_yesterday(tss: dict[str, float], today: date) -> dict | None:
    yesterday = today - timedelta(days=1)
    return compute_series(tss, yesterday, yesterday)[-1] if tss else None


def load_series(days: int) -> list[dict]:
    today = date.today()
    _, tss = load_context(today)
    return compute_series(tss, today - timedelta(days=days), today)


def recommendations(horizon: int) -> dict:
    today = date.today()
    settings = db.get_settings()
    activities, tss = load_context(today)
    full_series = compute_series(tss, today - timedelta(days=60), today)
    # Startzustand = Ende von gestern; heute Erledigtes wird in plan_days mitgezählt.
    state = {"ctl": 0.0, "atl": 0.0, "today_tss": tss.get(today.isoformat(), 0.0)}
    if (yesterday := _ctl_yesterday(tss, today)):
        state.update(ctl=yesterday["ctl"], atl=yesterday["atl"])
    # Workouts der ganzen betroffenen Wochen, damit die Wochenstunden richtig verteilt werden
    last_week_end = periodization.monday(today + timedelta(days=horizon - 1)) + timedelta(days=6)
    workouts = compliance.mark_matched(
        db.list_workouts(periodization.monday(today).isoformat(), last_week_end.isoformat()), activities, today, settings)
    wellness = db.get_wellness(today.isoformat())
    recent_workouts = db.list_workouts((today - timedelta(days=21)).isoformat(), today.isoformat())
    fb = feedback.evaluate(feedback.entries(recent_workouts, activities), state["ctl"] - state["atl"], today)
    races = db.list_races()
    return {
        "status": recommend.analyze(full_series, activities, wellness, settings, today, fb, races),
        "days": recommend.plan_days(settings, today, state, workouts, activities, wellness, horizon, fb, races),
    }


# --- Konflikte geplanter Workouts mit Wettkämpfen ----------------------------

def current_conflicts() -> list[dict]:
    today = date.today()
    race_list = conflicts.race_list(db.get_settings(), db.list_races())
    if not race_list:
        return []
    last = max(date.fromisoformat(r["date"]) for r in race_list) + timedelta(days=30)  # inkl. Erholung danach
    return conflicts.check(db.list_workouts(today.isoformat(), last.isoformat()), race_list, today)


def apply_conflicts(workout_ids: list[int]) -> dict:
    """Vorschläge für die gewählten Workouts übernehmen (neu geprüft, damit nichts Veraltetes geändert wird)."""
    applied, errors = [], []
    settings = db.get_settings()
    for c in current_conflicts():
        if c["workout_id"] not in workout_ids:
            continue
        if c["action"] == "delete":
            errors += [f"{c['date']} {c['name']} ({k}): {v}" for k, v in remove_workout(db.get_workout(c["workout_id"])).items()]
        else:
            res = store_workout(c["proposal"], settings)
            errors += [f"{c['date']} {c['name']} → {k}: {v}" for k, v in res["errors"].items()]
        applied.append({"workout_id": c["workout_id"], "date": c["date"], "action": c["action"]})
    return {"applied": applied, "errors": errors}


# --- Umfang & Ziele ------------------------------------------------------------

def _volume_data(start: date, end: date, settings: dict) -> tuple[list[dict], list[dict]]:
    activities = db.list_activities(start.isoformat(), end.isoformat())
    workouts = db.list_workouts(start.isoformat(), end.isoformat())
    return activities, compliance.mark_matched(workouts, activities, date.today(), settings)


def weeks(before: int | None, after: int | None) -> list[dict]:
    """Wochenstunden; ohne Angabe zwei ganze Belastungszyklen (vorheriger + laufender)."""
    today = date.today()
    settings = db.get_settings()
    if before is None or after is None:
        before, after = periodization.cycle_window(settings, today)
    monday = periodization.monday(today)
    activities, workouts = _volume_data(monday - timedelta(weeks=before), monday + timedelta(weeks=after, days=6), settings)
    return volume.weeks(settings, activities, workouts, today, before, after)


def week_summary(start: str) -> dict:
    """Wochenübersicht für die Kalender-Wochenansicht (Woche, in der `start` liegt)."""
    today = date.today()
    monday = periodization.monday(date.fromisoformat(start))
    sunday = monday + timedelta(days=6)
    settings = db.get_settings()
    activities = db.list_activities(monday.isoformat(), sunday.isoformat())
    workouts = compliance.mark_matched(db.list_workouts(monday.isoformat(), sunday.isoformat()), activities, today, settings)
    # Belastung am Ende der Woche: bisherige TSS plus geplante Workouts von heute bis Sonntag
    _, tss = load_context(today)
    if sunday >= today:
        upcoming = compliance.mark_matched(db.list_workouts(today.isoformat(), sunday.isoformat()),
                                           db.list_activities(today.isoformat(), today.isoformat()), today, settings)
        for w in upcoming:
            if w.get("status") != "done":
                tss[w["date"]] = tss.get(w["date"], 0.0) + estimate_tss(w)
    load = compute_series(tss, sunday, sunday)[-1] if tss else None
    return volume.week_summary(settings, monday, activities, workouts, today, load)


def goals() -> list[dict]:
    today = date.today()
    goal_list = db.list_goals()
    if not goal_list:
        return []
    ranges = [volume.period_range(g, today) for g in goal_list]
    activities, workouts = _volume_data(min(r[0] for r in ranges), max(r[1] for r in ranges), db.get_settings())
    return [volume.goal_progress(g, activities, workouts, today) for g in goal_list]


# --- Plan-Import und KI-Auftrag ----------------------------------------------

def parse_plan(plan: dict, start: str | None, warnings: list | None = None) -> tuple[list[dict], date, date]:
    try:
        return plan_import.parse(plan, date.today(), start, warnings)
    except plan_import.PlanError as e:
        raise ServiceError(str(e)) from e


def replaceable(first: date, last: date) -> list[dict]:
    """Geplante, nicht erledigte Workouts im Zeitraum (werden beim Import mit replace ersetzt)."""
    return [w for w in db.list_workouts(first.isoformat(), last.isoformat()) if w.get("status") != "done"]


def import_plan(plan: dict, start: str | None, replace: bool) -> dict:
    warnings: list[str] = []
    workouts, first, last = parse_plan(plan, start, warnings)
    errors = []
    removed = 0
    if replace:
        for w in replaceable(first, last):
            errors += [f"{w['date']} {w['name']} entfernen ({k}): {v}" for k, v in remove_workout(w).items()]
            removed += 1
    settings = db.get_settings()
    for w in workouts:
        res = store_workout(w, settings)
        errors += [f"{w['date']} {w['name']} → {k}: {v}" for k, v in res["errors"].items()]
    return {"created": len(workouts), "removed": removed, "start": first.isoformat(), "end": last.isoformat(),
            "errors": errors, "warnings": warnings}


def plan_brief(start: str, weeks_: int, notes: str | None) -> tuple[str, list[str], int]:
    """KI-Auftrag für einen Block → (Text, Fehler beim Lesen der Kalender, Anzahl Tage mit Terminen)."""
    today = date.today()
    first = periodization.monday(date.fromisoformat(start)) if start else plan_import.default_start(today)
    weeks_ = max(1, min(weeks_, 8))
    settings = db.get_settings()
    activities, tss = load_context(today)
    yesterday = _ctl_yesterday(tss, today)
    past = volume.weeks(settings, activities, [], today, before=4, after=0)[:-1] if activities else []
    busy, errors = availability.busy(settings.get("calendar_ics") or [], first, first + timedelta(weeks=weeks_, days=-1))
    text = plan_prompt.build(settings, first, weeks_, conflicts.race_list(settings, db.list_races()),
                             yesterday["ctl"] if yesterday else None, [w["done_hours"] for w in past], busy,
                             settings.get("availability", "") if notes is None else notes,
                             db.DEFAULT_SETTINGS["week_pattern"])
    return text, errors, len(busy)


# --- Garmin & andere Quellen -------------------------------------------------

def import_activities(source: str, days: int) -> int:
    if source not in ("garmin", "intervals"):
        raise ServiceError("Quelle muss garmin oder intervals sein")
    try:
        count = db.upsert_activities(TARGETS[source].import_activities(db.get_settings(), days))
        if source == "garmin":
            today = date.today().isoformat()
            db.upsert_wellness(today, TARGETS["garmin"].import_wellness(today))
    except Exception as e:  # noqa: BLE001
        raise ExternalError(f"Import fehlgeschlagen: {e}") from e
    return count


def refresh_settings_from_garmin() -> dict:
    """Leistungswerte aus Garmin übernehmen (die Oberfläche ruft das bei jedem Öffnen auf)."""
    settings = db.get_settings()
    garmin = TARGETS["garmin"]
    if not settings["garmin_profile"] or not garmin.is_connected():
        return {"changed": {}, "settings": settings}
    try:
        values = garmin.import_profile()
    except Exception as e:  # noqa: BLE001
        raise ExternalError(f"Garmin-Werte nicht abrufbar: {e}") from e
    # CSS: nur eine NEUE Garmin-Messung übernehmen (z. B. nach einem CSS-Test), nicht den eigenen Wert überschreiben
    css = values.pop("css_garmin", None)
    if css and css["at"] != settings["css_garmin_seen"]:
        if settings["css_garmin_seen"]:
            values["css"] = css["css"]
        values["css_garmin_seen"] = css["at"]
    changed = {k: v for k, v in values.items() if settings.get(k) != v and k != "css_garmin_seen"}
    stamp = datetime.now().isoformat(timespec="minutes") if values else settings["garmin_profile_at"]
    return {"changed": changed, "settings": db.save_settings({**values, "garmin_profile_at": stamp})}


def setup_garmin(email: str, password: str, code: str) -> dict:
    """Garmin aus dem Browser verbinden und Leistungswerte zum Vorausfüllen liefern (noch nicht gespeichert)."""
    garmin = TARGETS["garmin"]
    try:
        res = garmin.login_mfa(code) if code else garmin.login(email, password)
    except Exception as e:  # noqa: BLE001 – Meldung geht an die Oberfläche
        raise ServiceError(f"Garmin-Anmeldung fehlgeschlagen: {e}") from e
    if res["mfa"]:
        return res
    try:
        profile = garmin.import_profile()
    except Exception:  # noqa: BLE001 – Werte sind nur ein Vorschlag
        profile = {}
    css = profile.pop("css_garmin", None)
    if css:  # neue Nutzer: CSS sofort übernehmen und die Messung als gesehen merken
        profile.update(css=css["css"], css_garmin_seen=css["at"])
    return {**res, "profile": profile}


def _garmin_metrics(today: date, refresh: bool) -> tuple[dict | None, str | None, str | None]:
    """Garmin-Kennzahlen, 6 h zwischengespeichert → (Kennzahlen, Fehler, Abrufzeit)."""
    cached = db.get_cache("garmin_metrics")
    if cached and not refresh and datetime.now() - datetime.fromisoformat(cached[0]) < GARMIN_METRICS_MAX_AGE:
        return cached[1], None, cached[0]
    if not TARGETS["garmin"].is_connected():
        return None, None, None
    try:
        metrics = TARGETS["garmin"].import_metrics(today)
    except Exception as e:  # noqa: BLE001
        return (cached[1], str(e), cached[0]) if cached else (None, str(e), None)
    fetched_at = datetime.now().isoformat(timespec="minutes")
    db.set_cache("garmin_metrics", fetched_at, metrics)
    return metrics, None, fetched_at


def analysis_data(refresh: bool) -> dict:
    """Efficiency Factor, Zonen, Leistungskurve (aus importierten Aktivitäten) und Garmin-Kennzahlen."""
    today = date.today()
    activities = db.list_activities((today - timedelta(days=365)).isoformat(), today.isoformat())
    garmin_metrics, garmin_error, fetched_at = _garmin_metrics(today, refresh)
    settings = db.get_settings()
    ftp = settings["ftp"]
    # FTP am Tag der Einheit (Garmin-Verlauf), heute = Einstellung
    ftp_history = [{"date": e["date"], "watts": e["value"]} for e in (garmin_metrics or {}).get("ftp_series") or []]
    ftp_history.append({"date": today.isoformat(), "watts": ftp})
    return {
        "efficiency": analysis.ef_series(activities, today, ftp_history if len(ftp_history) > 1 else ftp,
                                         settings.get("threshold_pace") or 0),
        "zones": analysis.zone_weeks(activities, today),
        "power_curve": analysis.power_curve(activities, today, ftp),
        "garmin": garmin_metrics, "garmin_at": fetched_at, "garmin_error": garmin_error,
    }
