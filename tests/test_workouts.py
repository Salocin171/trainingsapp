"""Workout-Format, Dauer, TSS, Vorlagen und Zirkel-Timer."""
from datetime import date

import pytest

from app import db, templates
from app.sync import garmin
from app.workouts import estimate_tss, step, total_duration

from helpers import SETTINGS


def test_duration_and_tss(intervals_workout):
    assert total_duration(intervals_workout["steps"]) == 60 * 60
    # Eine Stunde konstant an der FTP = 100 TSS
    assert estimate_tss({"sport": "ride", "steps": [step("steady", 60, 100)]}) == 100


def test_build_for_tss_hits_target():
    w = templates.build_for_tss("endurance", "ride", 70)
    assert abs(estimate_tss(w) - 70) < 10


def test_circuit_settings(tmp_path):
    """Zirkel-Timer: Stabi-Vorlage bringt Übungen mit, Plan-Import prüft Grenzen, die API speichert den Zirkel."""
    from fastapi.testclient import TestClient
    from app import plan_import
    from app.main import app

    stabi = templates.build("stabi", "strength", 34)
    assert stabi["circuit"]["rounds"] == 2 and stabi["circuit"]["exercises"][0] == "Plank"
    assert all(e in stabi["description"] for e in stabi["circuit"]["exercises"])

    raw = {"sport": "strength", "template": "stabi", "minutes": 30,
           "circuit": {"work": 45, "rest": 15, "rounds": 60, "exercises": [
               "Burpees", " ", "Rudern | 12 Wdh", "Liegestütze | Wdh", "Wandsitz | 45 s", {"name": "Split Squat", "reps": 8}]}}
    circuit = plan_import.build_workout(raw, date(2026, 10, 29))["circuit"]
    assert circuit == {"work": 45, "rest": 15, "rounds": 60, "round_rest": 120, "exercises": [
        {"name": "Burpees"}, {"name": "Rudern", "reps": 12}, {"name": "Liegestütze", "reps": 0},
        {"name": "Wandsitz", "seconds": 45}, {"name": "Split Squat", "reps": 8}]}
    for bad, message in [({"rounds": 61}, "rounds: 61"), ({"exercises": [{"name": "X", "reps": 500}]}, "reps: 500")]:
        with pytest.raises(plan_import.PlanError, match=message):
            plan_import.build_workout({**raw, "circuit": bad}, date(2026, 10, 29))

    db.set_db_path(tmp_path / "circuit.db")
    client = TestClient(app)
    saved = client.post("/api/workouts", json={"date": "2026-10-29", "sport": "strength", "circuit": circuit}).json()
    assert db.get_workout(saved["workout"]["id"])["circuit"] == circuit


def test_step_target_survives_save_and_unknown_step_fields_are_rejected(tmp_path):
    from app import plan_import
    db.set_db_path(tmp_path / "t.db")
    w = plan_import.build_workout({"sport": "run", "target": "hr", "steps": "w10@70-80, 6x(i20s@95-103pace, r60s)"},
                                  date(2026, 11, 26))
    saved = db.get_workout(db.save_workout(w)["id"])
    on = saved["steps"][1]["steps"][0]
    assert on["target"] == "pace" and "target" not in saved["steps"][0]
    gs = garmin.to_garmin_json(saved, {**SETTINGS, "threshold_pace": 240})["workoutSegments"][0]["workoutSteps"]
    assert gs[0]["targetType"] == garmin.TARGET_TYPES["hr"]
    assert gs[1]["workoutSteps"][0]["targetType"] == garmin.TARGET_TYPES["pace"]
    with pytest.raises(plan_import.PlanError, match="target_type"):
        plan_import._steps([{"kind": "interval", "seconds": 20, "low": 95, "high": 103, "target_type": "pace"}], "T")
