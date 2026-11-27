"""Weitere Wettkämpfe (B/C). Das A-Rennen steht in den Einstellungen (goal_name, goal_date)."""
from datetime import date

from fastapi import APIRouter, HTTPException

from .. import db, races
from ..schemas import RaceIn

router = APIRouter(prefix="/api")


@router.get("/races")
def list_races():
    return db.list_races()


@router.get("/race-types")
def race_types():
    """Wettkampfdistanzen mit Taper- und Erholungstagen für B- und C-Priorität."""
    return races.catalog()


@router.post("/races")
def save_race(body: RaceIn):
    if body.priority not in ("B", "C") or body.race_type not in races.DISTANCES:
        raise HTTPException(400, f"Priorität B/C und eine Distanz aus {', '.join(races.DISTANCES)} erwartet")
    try:
        date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "Datum im Format JJJJ-MM-TT erwartet") from None
    return db.save_race(body.model_dump())


@router.delete("/races/{race_id}")
def delete_race(race_id: int):
    db.delete_race(race_id)
    return {"ok": True}
