"""Fixtures für alle Tests. Start: .venv/bin/python -m pytest"""
import pytest

from app import db
from app.workouts import repeat, step


@pytest.fixture(autouse=True)
def temp_database(tmp_path):
    """Jeder Test bekommt eine eigene leere Datenbank – nie die echte data/training.db."""
    previous = db._db_path
    db.set_db_path(tmp_path / "test.db")
    yield
    db.set_db_path(previous)


@pytest.fixture
def intervals_workout():
    return {
        "date": "2026-11-03", "sport": "ride", "name": "VO2 5x4", "target": "power", "id": 7,
        "steps": [
            step("warmup", 10, 50, 70),
            repeat(5, step("interval", 4, 110, 118), step("recovery", 4, 50, 55)),
            step("cooldown", 10, 50, 65),
        ],
    }
