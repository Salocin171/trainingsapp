"""Web-Server (FastAPI). Start: ./Trainingsapp.command oder
    .venv/bin/uvicorn app.main:app --reload --port 8765
"""
from datetime import date, datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analysis, compliance, config, conflicts, db, feedback, nutrition, periodization, plan_import, plan_prompt, races, recommend, templates, volume
from .load import compute_series, daily_tss
from .sync import TARGETS, status as sync_status, supports
from .workouts import summarize

app = FastAPI(title="Trainingsapp")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.middleware("http")
async def always_fresh_ui(request, call_next):
    """Oberfläche bei jedem Laden neu prüfen (ETag), damit der Browser nach Updates keine alte app.js nutzt."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")


# --- Workouts --------------------------------------------------------------

class WorkoutIn(BaseModel):
    id: int | None = None
    date: str
    sport: str = "ride"
    name: str = "Workout"
    description: str = ""
    target: str = "power"
    template: str = ""
    steps: list[dict] = []
    status: str = "planned"
    actual_tss: float | None = None
    rpe: float | None = None     # Anstrengung 0–10 (nach der Einheit)
    feel: int | None = None      # Befinden 1–5
    note: str = ""
    circuit: dict | None = None  # Zirkel-Timer: work/rest/round_rest (s), rounds, exercises


@app.get("/api/calendar")
def calendar(start: str, end: str):
    workouts = db.list_workouts(start[:10], end[:10])
    activities = db.list_activities(start[:10], end[:10])
    settings = db.get_settings()
    rating, unplanned, links = compliance.evaluate(workouts, activities, date.today(), settings)
    clash = {c["workout_id"]: c for c in conflicts.check(workouts, conflicts.race_list(settings, db.list_races()),
                                                         date.today())}
    races = [{"name": settings["goal_name"] or "Wettkampf", "date": settings["goal_date"], "priority": "A"}] \
        if settings.get("goal_date") else []
    races += db.list_races()
    return {
        "workouts": [{**summarize(w), "compliance": rating.get(w["id"]),
                      "conflict": {k: clash[w["id"]][k] for k in ("phase", "problem", "race")} if w["id"] in clash else None}
                     for w in workouts],
        "activities": [{**a, "unplanned": a["id"] in unplanned, "plan": links.get(a["id"])} for a in activities],
        "races": [r for r in races if start[:10] <= r["date"] <= end[:10]],
    }


class FeedbackIn(BaseModel):
    rpe: float | None = None
    feel: int | None = None
    note: str = ""


@app.put("/api/activities/{activity_id}/feedback")
def save_activity_feedback(activity_id: str, body: FeedbackIn):
    """RPE / Befinden / Notiz zu einer importierten Aktivität (leer = löschen)."""
    link = {k: v for k, v in db.get_feedback(activity_id).items() if k == "plan_link"}
    db.save_feedback(activity_id, link | {k: v for k, v in body.model_dump().items() if v not in (None, "")})
    return {"ok": True}


class PlanLinkIn(BaseModel):
    workout_id: int | None = None  # None = automatisch erkennen, 0 = gehört zu keinem Workout


@app.put("/api/activities/{activity_id}/plan")
def link_activity(activity_id: str, body: PlanLinkIn):
    """Zuordnung Aktivität ↔ geplantes Workout von Hand festlegen, wenn die Erkennung danebenliegt."""
    data = {k: v for k, v in db.get_feedback(activity_id).items() if k != "plan_link"}
    db.save_feedback(activity_id, data if body.workout_id is None else {**data, "plan_link": body.workout_id})
    return {"ok": True}


def _sync(workout: dict, targets: list[str]) -> dict:
    """An die gewünschten Ziele senden. Fehler pro Ziel sammeln statt abzubrechen."""
    settings = db.get_settings()
    sync = dict(workout.get("sync") or {})
    errors = {}
    for name in targets:
        try:
            sync[name] = TARGETS[name].push(workout, settings)
        except Exception as e:  # noqa: BLE001 – Fehlermeldung geht an die Oberfläche
            errors[name] = str(e)
    saved = db.save_workout({**workout, "sync": sync})
    return {"workout": summarize(saved), "errors": errors}


@app.post("/api/workouts")
def save_workout(body: WorkoutIn):
    existing = db.get_workout(body.id) if body.id else {}
    if body.id and not existing:
        raise HTTPException(404, "Workout nicht gefunden")
    return _store({**(existing or {}), **body.model_dump(exclude_none=False)})


def _store(data: dict) -> dict:
    """Workout speichern. Bereits übertragene Ziele aktuell halten, sonst Auto-Sync – nur wo der Sport passt
    und das Ziel eingerichtet ist (sonst käme bei jedem Speichern ein Fehler, z. B. ohne intervals.icu-Schlüssel)."""
    workout = db.save_workout(data)
    connected = sync_status()
    auto = {t for t in db.get_settings()["auto_sync"] if supports(t, workout.get("sport")) and connected.get(t)}
    targets = sorted(set((workout.get("sync") or {}).keys()) | auto)
    if workout.get("status") == "done" or not targets:
        return {"workout": summarize(workout), "errors": {}}
    return _sync(workout, targets)


class SyncIn(BaseModel):
    targets: list[str]


@app.get("/api/workouts/{workout_id}")
def get_workout(workout_id: int):
    workout = db.get_workout(workout_id)
    if not workout:
        raise HTTPException(404, "Workout nicht gefunden")
    return {**summarize(workout), "nutrition": nutrition.for_workout(workout, db.get_settings(), db.list_workouts)}


@app.post("/api/nutrition")
def nutrition_plan(body: WorkoutIn):
    """Verpflegung vor/während/nach einer (auch ungespeicherten) Einheit, z. B. für Vorschläge."""
    return nutrition.for_workout(body.model_dump(), db.get_settings(), db.list_workouts)


@app.post("/api/workouts/{workout_id}/sync")
def sync_workout(workout_id: int, body: SyncIn):
    workout = db.get_workout(workout_id)
    if not workout:
        raise HTTPException(404, "Workout nicht gefunden")
    unknown = set(body.targets) - TARGETS.keys()
    if unknown:
        raise HTTPException(400, f"Unbekannte Ziele: {unknown}")
    return _sync(workout, body.targets)


class BulkSyncIn(BaseModel):
    target: str
    days: int = 120   # ab heute


@app.post("/api/sync/bulk")
def bulk_sync(body: BulkSyncIn):
    """Alle geplanten, noch nicht übertragenen Workouts ab heute an ein Ziel senden (z. B. nach der Einrichtung)."""
    if body.target not in TARGETS:
        raise HTTPException(400, f"Unbekanntes Ziel: {body.target}")
    today = date.today()
    pending = [w for w in db.list_workouts(today.isoformat(), (today + timedelta(days=body.days)).isoformat())
               if w.get("status") != "done" and body.target not in (w.get("sync") or {})
               and supports(body.target, w.get("sport"))]
    errors = []
    for w in pending:
        errors += [f"{w['date']} {w['name']}: {e}" for e in _sync(w, [body.target])["errors"].values()]
    return {"sent": len(pending) - len(errors), "errors": errors}


@app.delete("/api/workouts/{workout_id}")
def delete_workout(workout_id: int):
    workout = db.get_workout(workout_id)
    if not workout:
        raise HTTPException(404, "Workout nicht gefunden")
    return {"ok": True, "errors": _remove(workout)}


def _remove(workout: dict) -> dict:
    """Workout löschen, auch auf den Geräten. Liefert Fehler pro Ziel."""
    errors = {}
    for name in (workout.get("sync") or {}):
        try:
            TARGETS[name].remove(workout)
        except Exception as e:  # noqa: BLE001
            errors[name] = str(e)
    db.delete_workout(workout["id"])
    return errors


# --- Plan-Import (z. B. 4-Wochen-Block als JSON) ----------------------------

class PlanIn(BaseModel):
    plan: dict
    start: str | None = None     # Montag der 1. Woche; überschreibt "start" im Plan
    replace: bool = False        # geplante (nicht erledigte) Workouts im Zeitraum vorher löschen


def _parse_plan(body: PlanIn, warnings: list | None = None):
    try:
        return plan_import.parse(body.plan, date.today(), body.start, warnings)
    except plan_import.PlanError as e:
        raise HTTPException(400, str(e)) from e


def _replaceable(first: date, last: date) -> list[dict]:
    return [w for w in db.list_workouts(first.isoformat(), last.isoformat()) if w.get("status") != "done"]


# Geprüfte Pläne für den Import per Kennung (MCP: Plan nur einmal senden, dann mit preview_id bestätigen)
_previews: dict[str, PlanIn] = {}


@app.post("/api/plan/preview")
def preview_plan(body: PlanIn):
    warnings: list[str] = []
    workouts, first, last = _parse_plan(body, warnings)
    preview_id = uuid4().hex[:8]
    _previews.clear()  # nur die letzte Vorschau merken
    _previews[preview_id] = body
    return {"workouts": [summarize(w) for w in workouts], "start": first.isoformat(), "end": last.isoformat(),
            "existing": len(_replaceable(first, last)), "warnings": warnings, "preview_id": preview_id}


@app.post("/api/plan/import/{preview_id}")
def import_previewed_plan(preview_id: str, replace: bool | None = None):
    """Zuletzt geprüften Plan importieren, ohne ihn erneut zu senden."""
    body = _previews.pop(preview_id, None)
    if body is None:
        raise HTTPException(404, "Vorschau nicht mehr vorhanden – Plan erneut prüfen")
    return import_plan(body if replace is None else body.model_copy(update={"replace": replace}))


@app.get("/api/plan/prompt", response_class=PlainTextResponse)
def plan_prompt_text(start: str = "", weeks: int = 4):
    """KI-Auftrag für einen Block (Text zum Kopieren in ChatGPT & Co.)."""
    today = date.today()
    first = periodization.monday(date.fromisoformat(start)) if start else plan_import.default_start(today)
    settings = db.get_settings()
    activities, tss = _load_context(today)
    ctl = compute_series(tss, today - timedelta(days=1), today - timedelta(days=1))[-1]["ctl"] if tss else None
    past = volume.weeks(settings, activities, [], today, before=4, after=0)[:-1] if activities else []
    return plan_prompt.build(settings, first, max(1, min(weeks, 8)),
                             conflicts.race_list(settings, db.list_races()), ctl, [w["done_hours"] for w in past])


@app.post("/api/plan/import")
def import_plan(body: PlanIn):
    warnings: list[str] = []
    workouts, first, last = _parse_plan(body, warnings)
    errors = []
    removed = 0
    if body.replace:
        for w in _replaceable(first, last):
            errors += [f"{w['date']} {w['name']} entfernen ({k}): {v}" for k, v in _remove(w).items()]
            removed += 1
    for w in workouts:
        res = _store(w)
        errors += [f"{w['date']} {w['name']} → {k}: {v}" for k, v in res["errors"].items()]
    return {"created": len(workouts), "removed": removed, "start": first.isoformat(), "end": last.isoformat(),
            "errors": errors, "warnings": warnings}


# --- Vorlagen --------------------------------------------------------------

@app.get("/api/templates")
def list_templates():
    return [{"key": k, "name": t.name, "min": t.min, "max": t.max, "hard": t.hard, "sports": t.sports}
            for k, t in templates.TEMPLATES.items()]


@app.get("/api/templates/{kind}")
def build_template(kind: str, sport: str = "ride", minutes: int = 60):
    if kind not in templates.TEMPLATES:
        raise HTTPException(404, "Unbekannte Vorlage")
    return summarize(templates.build(kind, sport, minutes))


# --- Belastung & Empfehlungen ---------------------------------------------

def _load_context(today: date):
    history_start = today - timedelta(days=180)
    activities = db.list_activities(history_start.isoformat(), today.isoformat())
    past_workouts = db.list_workouts(history_start.isoformat(), today.isoformat())
    tss = daily_tss(activities, past_workouts)
    return activities, tss


@app.get("/api/load")
def load(days: int = 90):
    today = date.today()
    _, tss = _load_context(today)
    return compute_series(tss, today - timedelta(days=days), today)


@app.get("/api/recommendations")
def recommendations(horizon: int = 7):
    today = date.today()
    settings = db.get_settings()
    activities, tss = _load_context(today)
    full_series = compute_series(tss, today - timedelta(days=60), today)
    # Startzustand = Ende von gestern; heute Erledigtes wird in plan_days mitgezählt.
    state = {"ctl": 0.0, "atl": 0.0, "today_tss": tss.get(today.isoformat(), 0.0)}
    if tss:
        yesterday = compute_series(tss, today - timedelta(days=1), today - timedelta(days=1))[-1]
        state.update(ctl=yesterday["ctl"], atl=yesterday["atl"])
    # Workouts der ganzen betroffenen Wochen, damit die Wochenstunden richtig verteilt werden
    last_week_end = periodization.monday(today + timedelta(days=horizon - 1)) + timedelta(days=6)
    workouts = compliance.mark_matched(db.list_workouts(periodization.monday(today).isoformat(), last_week_end.isoformat()),
                                       activities, today, settings)
    wellness = db.get_wellness(today.isoformat())
    recent_workouts = db.list_workouts((today - timedelta(days=21)).isoformat(), today.isoformat())
    fb = feedback.evaluate(feedback.entries(recent_workouts, activities), state["ctl"] - state["atl"], today)
    races = db.list_races()
    return {
        "status": recommend.analyze(full_series, activities, wellness, settings, today, fb, races),
        "days": recommend.plan_days(settings, today, state, workouts, activities, wellness, horizon, fb, races),
    }


# --- Konflikte geplanter Workouts mit Wettkämpfen ---------------------------

def _current_conflicts() -> list[dict]:
    today = date.today()
    race_list = conflicts.race_list(db.get_settings(), db.list_races())
    if not race_list:
        return []
    last = max(date.fromisoformat(r["date"]) for r in race_list) + timedelta(days=30)  # inkl. Erholung danach
    return conflicts.check(db.list_workouts(today.isoformat(), last.isoformat()), race_list, today)


@app.get("/api/conflicts")
def list_conflicts():
    """Geplante Workouts, die nicht zu Taper/Erholung eines Wettkampfs passen – mit Änderungsvorschlag."""
    return [{**c, "proposal": summarize(c["proposal"]) if c["proposal"] else None} for c in _current_conflicts()]


class ApplyConflictsIn(BaseModel):
    workout_ids: list[int]


@app.post("/api/conflicts/apply")
def apply_conflicts(body: ApplyConflictsIn):
    """Vorschläge für die gewählten Workouts übernehmen (neu geprüft, damit nichts Veraltetes geändert wird)."""
    applied, errors = [], []
    for c in _current_conflicts():
        if c["workout_id"] not in body.workout_ids:
            continue
        workout = db.get_workout(c["workout_id"])
        if c["action"] == "delete":
            errors += [f"{c['date']} {c['name']} ({k}): {v}" for k, v in _remove(workout).items()]
        else:
            res = _store(c["proposal"])
            errors += [f"{c['date']} {c['name']} → {k}: {v}" for k, v in res["errors"].items()]
        applied.append({"workout_id": c["workout_id"], "date": c["date"], "action": c["action"]})
    return {"applied": applied, "errors": errors}


# --- Wettkämpfe (B/C) ------------------------------------------------------

class RaceIn(BaseModel):
    id: int | None = None
    name: str
    date: str
    priority: str = "B"          # B = Mini-Taper + Erholung, C = durchtrainieren
    race_type: str = "other"     # Schlüssel aus races.DISTANCES (z. B. run_marathon, half) → Taper/Erholung


@app.get("/api/races")
def list_races():
    return db.list_races()


@app.get("/api/race-types")
def race_types():
    """Wettkampfdistanzen mit Taper- und Erholungstagen für B- und C-Priorität."""
    return races.catalog()


@app.post("/api/races")
def save_race(body: RaceIn):
    if body.priority not in ("B", "C") or body.race_type not in races.DISTANCES:
        raise HTTPException(400, f"Priorität B/C und eine Distanz aus {', '.join(races.DISTANCES)} erwartet")
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "Datum im Format JJJJ-MM-TT erwartet") from None
    return db.save_race(body.model_dump())


@app.delete("/api/races/{race_id}")
def delete_race(race_id: int):
    db.delete_race(race_id)
    return {"ok": True}


# --- Umfang & Ziele --------------------------------------------------------

def _volume_data(start: date, end: date):
    activities = db.list_activities(start.isoformat(), end.isoformat())
    workouts = db.list_workouts(start.isoformat(), end.isoformat())
    return activities, compliance.mark_matched(workouts, activities, date.today(), db.get_settings())


@app.get("/api/weeks")
def weeks(before: int = 3, after: int = 2):
    today = date.today()
    monday = periodization.monday(today)
    activities, workouts = _volume_data(monday - timedelta(weeks=before), monday + timedelta(weeks=after, days=6))
    return volume.weeks(db.get_settings(), activities, workouts, today, before, after)


class GoalIn(BaseModel):
    id: int | None = None
    name: str = ""
    sport: str = "all"          # all | swim | ride | run | strength | mobility
    metric: str = "hours"       # hours | km
    period: str = "week"        # week | month | year | custom
    target: float
    start: str = ""             # nur bei period = custom
    end: str = ""


@app.get("/api/goals")
def list_goals():
    today = date.today()
    goals = db.list_goals()
    if not goals:
        return []
    ranges = [volume.period_range(g, today) for g in goals]
    activities, workouts = _volume_data(min(r[0] for r in ranges), max(r[1] for r in ranges))
    return [volume.goal_progress(g, activities, workouts, today) for g in goals]


@app.post("/api/goals")
def save_goal(body: GoalIn):
    if body.period not in volume.GOAL_PERIODS or body.metric not in volume.GOAL_METRICS:
        raise HTTPException(400, "Unbekannter Zeitraum oder Einheit")
    if body.period == "custom" and not (body.start and body.end and body.start <= body.end):
        raise HTTPException(400, "Für einen eigenen Zeitraum Start- und Enddatum angeben")
    return db.save_goal(body.model_dump())


@app.delete("/api/goals/{goal_id}")
def delete_goal(goal_id: int):
    db.delete_goal(goal_id)
    return {"ok": True}


# --- Import ----------------------------------------------------------------

@app.post("/api/import/{source}")
def import_data(source: str, days: int = 120):
    if source not in ("garmin", "intervals"):
        raise HTTPException(400, "Quelle muss garmin oder intervals sein")
    settings = db.get_settings()
    try:
        items = TARGETS[source].import_activities(settings, days)
        count = db.upsert_activities(items)
        if source == "garmin":
            today = date.today().isoformat()
            db.upsert_wellness(today, TARGETS["garmin"].import_wellness(today))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Import fehlgeschlagen: {e}") from e
    return {"imported": count}


# --- Einstellungen & Status ----------------------------------------------

@app.get("/api/settings")
def get_settings():
    return db.get_settings()


@app.put("/api/settings")
def put_settings(values: dict):
    return db.save_settings(values)


@app.post("/api/settings/garmin")
def refresh_settings_from_garmin():
    """Leistungswerte aus Garmin übernehmen (die Oberfläche ruft das bei jedem Öffnen auf)."""
    settings = db.get_settings()
    if not settings["garmin_profile"] or not TARGETS["garmin"].is_connected():
        return {"changed": {}, "settings": settings}
    try:
        values = TARGETS["garmin"].import_profile()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Garmin-Werte nicht abrufbar: {e}") from e
    # CSS: nur eine NEUE Garmin-Messung übernehmen (z. B. nach einem CSS-Test), nicht den eigenen Wert überschreiben
    css = values.pop("css_garmin", None)
    if css and css["at"] != settings["css_garmin_seen"]:
        if settings["css_garmin_seen"]:
            values["css"] = css["css"]
        values["css_garmin_seen"] = css["at"]
    changed = {k: v for k, v in values.items() if settings.get(k) != v and k != "css_garmin_seen"}
    stamp = datetime.now().isoformat(timespec="minutes") if values else settings["garmin_profile_at"]
    return {"changed": changed, "settings": db.save_settings({**values, "garmin_profile_at": stamp})}


GARMIN_METRICS_MAX_AGE = timedelta(hours=6)


@app.get("/api/analysis")
def get_analysis(refresh: bool = False):
    """Efficiency Factor, Zonen, Leistungskurve (aus importierten Aktivitäten) und Garmin-Kennzahlen (gecacht)."""
    today = date.today()
    activities = db.list_activities((today - timedelta(days=365)).isoformat(), today.isoformat())
    garmin_metrics, garmin_error, fetched_at = None, None, None
    cached = db.get_cache("garmin_metrics")
    if cached and not refresh and datetime.now() - datetime.fromisoformat(cached[0]) < GARMIN_METRICS_MAX_AGE:
        fetched_at, garmin_metrics = cached
    elif TARGETS["garmin"].is_connected():
        try:
            garmin_metrics = TARGETS["garmin"].import_metrics(today)
            fetched_at = datetime.now().isoformat(timespec="minutes")
            db.set_cache("garmin_metrics", fetched_at, garmin_metrics)
        except Exception as e:  # noqa: BLE001
            garmin_error = str(e)
            if cached:
                fetched_at, garmin_metrics = cached
    return {
        "efficiency": analysis.ef_series(activities, today),
        "zones": analysis.zone_weeks(activities, today),
        "power_curve": analysis.power_curve(activities, today, db.get_settings()["ftp"]),
        "garmin": garmin_metrics, "garmin_at": fetched_at, "garmin_error": garmin_error,
    }


# --- Einrichtung (erster Start) ---------------------------------------------

class GarminLoginIn(BaseModel):
    email: str = ""
    password: str = ""
    code: str = ""  # MFA-Code im zweiten Schritt


@app.post("/api/setup/garmin")
def setup_garmin(body: GarminLoginIn):
    """Garmin aus dem Browser verbinden und Leistungswerte zum Vorausfüllen liefern (noch nicht gespeichert)."""
    garmin = TARGETS["garmin"]
    try:
        res = garmin.login_mfa(body.code) if body.code else garmin.login(body.email, body.password)
    except Exception as e:  # noqa: BLE001 – Meldung geht an die Oberfläche
        raise HTTPException(400, f"Garmin-Anmeldung fehlgeschlagen: {e}") from e
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


@app.get("/api/status")
def get_status():
    return sync_status()
