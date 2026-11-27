"""Kalender, Workouts, Übertragung an Geräte, Feedback zu Aktivitäten, Vorlagen."""
from fastapi import APIRouter, HTTPException

from .. import db, services, templates
from ..schemas import BulkSyncIn, FeedbackIn, PlanLinkIn, SyncIn, WorkoutIn
from ..sync import TARGETS
from ..workouts import summarize
from . import workout_or_404

router = APIRouter(prefix="/api")


@router.get("/calendar")
def calendar(start: str, end: str):
    return services.calendar(start[:10], end[:10])


@router.post("/workouts")
def save_workout(body: WorkoutIn):
    existing = db.get_workout(body.id) if body.id else {}
    if body.id and not existing:
        raise HTTPException(404, "Workout nicht gefunden")
    return services.store_workout({**(existing or {}), **body.model_dump()})


@router.get("/workouts/{workout_id}")
def get_workout(workout_id: int):
    return services.workout_details(workout_or_404(workout_id))


@router.delete("/workouts/{workout_id}")
def delete_workout(workout_id: int):
    return {"ok": True, "errors": services.remove_workout(workout_or_404(workout_id))}


@router.post("/workouts/{workout_id}/sync")
def sync_workout(workout_id: int, body: SyncIn):
    workout = workout_or_404(workout_id)
    unknown = set(body.targets) - TARGETS.keys()
    if unknown:
        raise HTTPException(400, f"Unbekannte Ziele: {unknown}")
    return services.sync_workout(workout, body.targets)


@router.post("/sync/bulk")
def bulk_sync(body: BulkSyncIn):
    return services.bulk_sync(body.target, body.days, body.resend)


@router.post("/nutrition")
def nutrition_plan(body: WorkoutIn):
    """Verpflegung vor/während/nach einer (auch ungespeicherten) Einheit, z. B. für Vorschläge."""
    return services.nutrition_plan(body.model_dump())


@router.put("/activities/{activity_id}/feedback")
def save_activity_feedback(activity_id: str, body: FeedbackIn):
    """RPE / Befinden / Notiz zu einer importierten Aktivität (leer = löschen)."""
    services.save_activity_feedback(activity_id, body.model_dump())
    return {"ok": True}


@router.put("/activities/{activity_id}/plan")
def link_activity(activity_id: str, body: PlanLinkIn):
    """Zuordnung Aktivität ↔ geplantes Workout von Hand festlegen, wenn die Erkennung danebenliegt."""
    services.link_activity(activity_id, body.workout_id)
    return {"ok": True}


@router.get("/activities/{activity_id}/laps")
def activity_laps(activity_id: str):
    """Abschnitte einer Aktivität: Zwischenzeiten, Puls und Pace/Leistung je Intervall, mit Ziel aus dem Plan."""
    try:
        return services.activity_laps(activity_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None


@router.get("/templates")
def list_templates():
    return [{"key": k, "name": t.name, "min": t.min, "max": t.max, "hard": t.hard, "sports": t.sports}
            for k, t in templates.TEMPLATES.items()]


@router.get("/templates/{kind}")
def build_template(kind: str, sport: str = "ride", minutes: int = 60):
    if kind not in templates.TEMPLATES:
        raise HTTPException(404, "Unbekannte Vorlage")
    return summarize(templates.build(kind, sport, minutes))
