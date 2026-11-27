"""HTTP-Routen, ein Modul je Bereich. Jede Route prüft die Eingabe (schemas.py), ruft services bzw. db auf und
liefert JSON. ServiceError/ExternalError aus den Services werden in main.py zu 400/502."""
from fastapi import HTTPException

from .. import db


def workout_or_404(workout_id: int) -> dict:
    workout = db.get_workout(workout_id)
    if not workout:
        raise HTTPException(404, "Workout nicht gefunden")
    return workout
