"""Übertragung an Garmin, intervals.icu, Zwift und die Kalender-App."""
from xml.etree import ElementTree

import pytest

from app import db, templates
from app.sync import garmin, intervals, zwift
from app.workouts import repeat, step

from helpers import SETTINGS


def test_zwo_is_valid_xml_with_intervals(intervals_workout):
    root = ElementTree.fromstring(zwift.to_zwo(intervals_workout))
    blocks = root.find("workout")
    assert [b.tag for b in blocks] == ["Warmup", "IntervalsT", "Cooldown"]
    assert blocks[1].get("Repeat") == "5"
    assert float(blocks[1].get("OnPower")) == pytest.approx(1.14)


def test_garmin_json_uses_watts_and_repeat_group(intervals_workout):
    data = garmin.to_garmin_json(intervals_workout, {**SETTINGS, "ftp": 300})
    steps = data["workoutSegments"][0]["workoutSteps"]
    assert steps[1]["type"] == "RepeatGroupDTO" and steps[1]["numberOfIterations"] == 5
    work = steps[1]["workoutSteps"][0]
    assert (work["targetValueOne"], work["targetValueTwo"]) == (330, 354)


def test_garmin_profile_parsing():
    # Antwortformat wie von Garmin Connect geliefert (gekürzt)
    profile = garmin.parse_profile(
        [{"sport": "CYCLING", "functionalThresholdPower": 353}],
        {"speed_and_heart_rate": {"speed": 0.41388773, "heartRate": 185, "heartRateCycling": 183},
         "power": {"weight": 85.0}},
        [{"sport": "DEFAULT", "maxHeartRateUsed": 203}, {"sport": "CYCLING", "maxHeartRateUsed": 200}],
    )
    assert profile == {"ftp": 353, "lthr_run": 185, "lthr_ride": 183, "threshold_pace": 242, "max_hr": 203,
                       "weight": 85.0}
    assert garmin.parse_profile(None, None, None) == {}


def test_intervals_text(intervals_workout):
    text = intervals.to_text(intervals_workout)
    assert "- 10m ramp 50-70%" in text
    assert "5x\n- 4m 110-118%\n- 4m 50-55%" in text


def test_intervals_text_without_target():
    text = intervals.to_text({"sport": "strength", "steps": [step("interval", 10, 0)]})
    assert text == "- 10m"


def test_steps_can_use_their_own_target():
    """Einlaufen nach Puls, Intervalle nach Pace – unabhängig vom Ziel des Workouts."""
    from app import plan_import
    from app.sync import maccal
    settings = {**SETTINGS, "lthr_run": 170, "threshold_pace": 240}
    run = {"sport": "run", "name": "Tempo", "target": "pace", "steps": [
        step("warmup", 15, 70, 80) | {"target": "hr"},
        repeat(4, step("interval", 4, 100), step("recovery", 2, 60, 70) | {"target": "hr"}),
    ]}
    first, rep = garmin.to_garmin_json(run, settings)["workoutSegments"][0]["workoutSteps"]
    assert first["targetType"] == garmin.TARGET_TYPES["hr"] and first["targetValueOne"] == pytest.approx(119)
    on, off = rep["workoutSteps"]
    assert on["targetType"] == garmin.TARGET_TYPES["pace"] and on["targetValueOne"] == pytest.approx(1000 / 240, abs=0.001)
    assert off["targetType"] == garmin.TARGET_TYPES["hr"]
    text = maccal.event_text(run, settings)[1]
    assert "119–136 bpm" in text and "4:00 /km" in text
    assert "- 15m ramp 70-80% LTHR" in intervals.to_text(run)
    assert "- 4m 100% Pace" in intervals.to_text(run)
    steps = plan_import.compact_steps("w15@70-80hr, 4x(i4@100, r2@60-70 puls)", "Test")
    assert steps[0]["target"] == "hr" and "target" not in steps[1]["steps"][0]
    assert plan_import._steps("w15@70-80hr, i4@100", "Test")[0]["target"] == "hr"
    with pytest.raises(plan_import.PlanError):
        plan_import._steps([{"kind": "steady", "minutes": 5, "low": 70, "target": "rpe"}], "Test")


def test_swim_target_uses_css():
    workout = {"sport": "swim", "target": "pace", "steps": [step("steady", 10, 100)]}
    target = garmin.to_garmin_json(workout, {**SETTINGS, "css": 86})["workoutSegments"][0]["workoutSteps"][0]
    assert target["targetValueOne"] == pytest.approx(100 / 86, abs=0.001)


def test_garmin_strength_circuit():
    """Stabi geht als Zirkel an Garmin: je Übung ein Schritt mit Katalog-Übung, Pausen, Rundenpause."""
    workout = {"date": "2026-10-29", "status": "planned", **templates.build("stabi", "strength", 34)}
    j = garmin.to_garmin_json(workout, db.DEFAULT_SETTINGS)
    warm, rounds, cool = j["workoutSegments"][0]["workoutSteps"]
    assert (rounds["numberOfIterations"], rounds["skipLastRestStep"]) == (2, True)
    first, rest = rounds["workoutSteps"][:2]
    assert (first["description"], first["category"], first["exerciseName"], first["endConditionValue"]) == ("Plank", "PLANK", "PLANK", 40)
    assert (rest["stepType"]["stepTypeKey"], rest["endConditionValue"]) == ("rest", 20)
    assert rounds["workoutSteps"][-1]["endConditionValue"] == 120  # Rundenpause
    assert "category" not in garmin.exercise("Bird Dog") and garmin.exercise("Bird Dog")["description"] == "Bird Dog"
    assert garmin.exercise("Kniebeugen einbeinig")["exerciseName"] == "PARTIAL_SINGLE_LEG_SQUAT"
    reps = {**workout, "circuit": {"work": 50, "rest": 0, "rounds": 1, "round_rest": 0, "exercises": [
        {"name": "Split Squat", "reps": 8}, {"name": "Liegestütze", "reps": 0}, {"name": "Wandsitz", "seconds": 45}]}}
    split, push, wall = garmin.to_garmin_json(reps, db.DEFAULT_SETTINGS)["workoutSegments"][0]["workoutSteps"][1]["workoutSteps"]
    assert (split["endCondition"]["conditionTypeKey"], split["endConditionValue"]) == ("reps", 8)
    assert push["endCondition"]["conditionTypeKey"] == "lap.button" and "endConditionValue" not in push
    assert (wall["endCondition"]["conditionTypeKey"], wall["endConditionValue"]) == ("time", 45)
    ride = garmin.to_garmin_json({"sport": "ride", "steps": [repeat(2, step("interval", 1, 100))]}, db.DEFAULT_SETTINGS)
    assert ride["workoutSegments"][0]["workoutSteps"][0]["skipLastRestStep"] is False


def test_calendar_event_text():
    from app.sync import maccal

    w = {"id": 5, "date": "2026-11-03", "sport": "ride", "target": "power", "name": "Sweet Spot 3x12",
         "description": "Knapp unter der Schwelle.",
         "steps": [step("warmup", 15, 50, 75), repeat(3, step("interval", 12, 88, 93), step("recovery", 5, 50, 55))]}
    title, text = maccal.event_text(w, {**SETTINGS, "ftp": 300})
    assert title == "Radfahren – Sweet Spot 3x12"
    assert "1:06 h" in text and not text.startswith("Sweet Spot")
    assert "• 12 min Intervall – 264–279 W" in text and "3×" in text
    run = {**w, "sport": "run", "target": "pace", "steps": [step("steady", 30, 80, 80)]}
    assert "5:15 /km" in maccal.event_text(run, {**SETTINGS, "threshold_pace": 252})[1]
    swim = {**w, "sport": "swim", "target": "pace", "steps": [step("interval", 4, 100, 100), step("recovery", 0.5, 0)]}
    text = maccal.event_text(swim, {**SETTINGS, "css": 86})[1]
    assert "1:26 /100 m" in text and "• 30 s Erholung\n" in text + "\n"


def test_calendar_title_short_program_long_in_description():
    from app.sync import maccal

    def text(sport, name):
        return maccal.event_text({"date": "2026-11-03", "sport": sport, "name": name, "steps": []}, SETTINGS)

    assert text("run", "Locker 40")[0] == "Laufen – Locker 40"
    title, desc = text("ride", "FTP-Test 20 min (nur bei HRV ok, sonst 75 min Z2)")
    assert title == "Radfahren – FTP-Test 20 min" and desc.startswith("FTP-Test 20 min (nur bei HRV ok, sonst 75 min Z2)")
    title, desc = text("swim", "Technik & Speed: 3x(4x100 @103-108%) + Pull + 8x50")
    assert title == "Schwimmen – Technik & Speed" and "3x(4x100" in desc
    title, desc = text("run", "10x30 s @ 3:45-3:55/km / 90 s Traben")
    assert title == "Laufen" and desc.startswith("10x30 s @")
    assert text("strength", "Stabi / Kraft")[0] == "Stabi / Kraft"


def test_calendar_push_update_move_remove(monkeypatch):
    from app.sync import maccal

    calls = []

    def fake(script, *args, timeout=120):
        calls.append((script, args))
        return "UID-1" if script is maccal._PUSH else ""

    monkeypatch.setattr(maccal, "_osascript", fake)
    monkeypatch.setattr(maccal.sys, "platform", "darwin")
    w = {"id": 1, "date": "2026-11-03", "sport": "run", "name": "Locker", "steps": [step("steady", 40, 75)]}
    settings = {**SETTINGS, "mac_calendar": "Trainingsplan"}
    first = maccal.push(w, settings)
    assert first == {"uid": "UID-1", "calendar": "Trainingsplan"}
    assert calls[0][1][:3] == ("Trainingsplan", "Trainingsplan", "") and calls[0][1][-3:] == ("2026", "11", "3")
    maccal.push({**w, "sync": {"calendar": first}}, settings)            # ändern: gleiche uid
    assert calls[1][1][2] == "UID-1"
    maccal.push({**w, "sync": {"calendar": first}}, {**settings, "mac_calendar": "Sport"})  # Kalender gewechselt
    assert calls[2][1][:3] == ("Sport", "Trainingsplan", "UID-1")
    maccal.remove({**w, "sync": {"calendar": first}})
    assert calls[3] == (maccal._REMOVE, ("Trainingsplan", "UID-1"))
    with pytest.raises(RuntimeError, match="Kein Kalender gewählt"):
        maccal.push(w, {**SETTINGS, "mac_calendar": ""})


def test_calendar_script_keeps_allday_events_one_day():
    """Kalender-App: allday zuletzt bzw. Ende = Start + 1 Tag ergab 2-Tage-Termine; Datum per „set start date“
    zu ändern ebenso (bzw. Fehler beim Verschieben nach hinten) – getestet gegen die echte Kalender-App."""
    from app.sync import maccal

    make = next(line for line in maccal._PUSH.splitlines() if "make new event" in line)
    assert "with properties {allday event:true," in make and "end date:dt}" in make
    assert "set start date" not in maccal._PUSH and "set end date" not in maccal._PUSH


def test_calendar_pauses_after_missing_permission(monkeypatch):
    """Fehlt die macOS-Berechtigung, hängt nicht jedes Speichern: Pause, Auto-Sync überspringt, Auswahl fragt neu."""
    import subprocess

    from app.sync import maccal

    runs = []

    def hang(cmd, **kw):
        runs.append(cmd)
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    monkeypatch.setattr(maccal.sys, "platform", "darwin")
    monkeypatch.setattr(maccal.subprocess, "run", hang)
    monkeypatch.setattr(maccal, "_blocked_until", 0.0)
    w = {"id": 1, "date": "2026-11-03", "sport": "run", "name": "Locker", "steps": [step("steady", 40, 75)]}
    with pytest.raises(RuntimeError, match="antwortet nicht"):
        maccal.push(w, {**SETTINGS, "mac_calendar": "Trainingsplan"})
    with pytest.raises(RuntimeError, match="antwortet nicht"):   # zweiter Versuch wartet nicht erneut
        maccal.push(w, {**SETTINGS, "mac_calendar": "Trainingsplan"})
    assert len(runs) == 1
    monkeypatch.setattr(maccal.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "Trainingsplan\ttrue\n", ""))
    assert maccal.calendars() == [{"name": "Trainingsplan", "writable": True}]  # Auswahl fragt trotz Pause neu
    assert maccal._blocked_until == 0.0


def test_status_uses_zwift_folder_from_settings(tmp_path, monkeypatch):
    from app import sync

    monkeypatch.setattr(zwift, "ZWIFT_ROOT", tmp_path / "gibt-es-nicht")
    assert sync.status({**SETTINGS, "zwift_dir": str(tmp_path)})["zwift"] is True
    assert sync.status({**SETTINGS, "zwift_dir": str(tmp_path / "fehlt")})["zwift"] is False
    assert sync.status(SETTINGS)["zwift"] is False
