"""Belastung, Vorschläge, Konflikte mit Wettkämpfen, Wochenstunden und Ziele (Seitenleiste)."""
from fastapi import APIRouter, HTTPException

from .. import db, services, volume
from ..schemas import ApplyConflictsIn, GoalIn
from ..workouts import summarize

router = APIRouter(prefix="/api")


@router.get("/load")
def load(days: int = 90):
    return services.load_series(days)


@router.get("/recommendations")
def recommendations(horizon: int = 7):
    return services.recommendations(horizon)


@router.get("/conflicts")
def list_conflicts():
    """Geplante Workouts, die nicht zu Taper/Erholung eines Wettkampfs passen – mit Änderungsvorschlag."""
    return [{**c, "proposal": summarize(c["proposal"]) if c["proposal"] else None} for c in services.current_conflicts()]


@router.post("/conflicts/apply")
def apply_conflicts(body: ApplyConflictsIn):
    return services.apply_conflicts(body.workout_ids)


@router.get("/weeks")
def weeks(before: int | None = None, after: int | None = None):
    """Wochenstunden; ohne Angabe zwei ganze Belastungszyklen (vorheriger + laufender)."""
    return services.weeks(before, after)


@router.get("/goals")
def list_goals():
    return services.goals()


@router.post("/goals")
def save_goal(body: GoalIn):
    if body.period not in volume.GOAL_PERIODS or body.metric not in volume.GOAL_METRICS:
        raise HTTPException(400, "Unbekannter Zeitraum oder Einheit")
    if body.period == "custom" and not (body.start and body.end and body.start <= body.end):
        raise HTTPException(400, "Für einen eigenen Zeitraum Start- und Enddatum angeben")
    return db.save_goal(body.model_dump())


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: int):
    db.delete_goal(goal_id)
    return {"ok": True}
