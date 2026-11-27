"""Abschnitte einer Aktivität: Runden nach Workout-Schritten, Verlauf nach Plan, Schwimmserien, Garmin-Format."""
import pytest

from app import laps
from app.sync import garmin
from app.workouts import repeat, step

from helpers import SETTINGS

RUN_SETTINGS = {**SETTINGS, "threshold_pace": 240, "ftp": 300, "css": 100}

# 2 × 1000 m mit Trabpause, wie es die Uhr mit Workout liefert: Auto-Runde 1 km + Rest gehören zu einem Schritt
TRACK = {"id": 7, "sport": "run", "name": "2×1000", "target": "pace", "steps": [
    step("warmup", 10, 70, 78), repeat(2, step("interval", 4, 99, 101), step("recovery", 2, 60, 70)), step("cooldown", 5, 65, 75)]}


def lap(kind, step_index, duration, distance, hr, **extra):
    return {"kind": kind, "step": step_index, "duration": duration, "distance": distance,
            "speed": distance / duration if distance else None, "hr": hr, "max_hr": hr + 5, **extra}


def test_fit_steps_number_repeat_groups_after_their_steps():
    order = laps.fit_steps(TRACK["steps"])
    assert [s and s["kind"] for s in order] == ["warmup", "interval", "recovery", None, "cooldown"]


def test_laps_of_the_same_step_are_merged_and_rated_against_the_plan():
    run_laps = [
        lap("warmup", 0, 600, 1900, 140),
        lap("interval", 1, 235, 1000, 180), lap("interval", 1, 5, 20, 182),       # 1 km Auto-Runde + Rest
        lap("recovery", 2, 120, 300, 160),
        lap("interval", 1, 250, 1000, 184),                                      # zu langsam: 4:10/km
        lap("recovery", 2, 120, 280, 162),
        lap("cooldown", 4, 300, 800, 150),
    ]
    activity = {"id": "garmin:1", "sport": "run", "distance": 5300, "duration": 1630, "metrics": {"avg_hr": 165}}
    res = laps.build(activity, run_laps, None, TRACK, RUN_SETTINGS)
    assert res["source"] == "steps" and len(res["segments"]) == 6
    first = res["segments"][1]
    assert (first["kind"], first["rep"], first["duration"], first["distance"], first["laps"]) == ("interval", "1/2", 240, 1020, 2)
    assert first["hr"] == pytest.approx(180.0, abs=0.1) and first["max_hr"] == 187
    # Ziel 99–101 % von 4:00/km = 4,125–4,208 m/s; 1020 m in 240 s = 4,25 m/s liegt im 2-%-Spielraum
    assert first["target"]["type"] == "pace" and first["in_target"] is True
    assert res["segments"][3]["in_target"] is False
    assert "in_target" not in res["segments"][2]                                # Trabpause wird nicht bewertet
    summary = res["intervals"][0]
    assert (summary["count"], summary["in_target"], summary["rated"], summary["avg_distance"]) == (2, 1, 2, 1010)
    assert res["total"]["hr"] == 165 and res["workout"] == {"id": 7, "name": "2×1000"}


def test_ride_without_workout_on_the_device_is_cut_by_the_plan():
    plan = {"id": 3, "sport": "ride", "target": "power", "steps": [
        step("warmup", 2, 50, 60), repeat(2, step("interval", 3, 90, 95), step("recovery", 1, 50, 55))]}
    t = list(range(0, 600, 5))
    power = [150 if x < 120 else 280 if (x - 120) % 240 < 180 else 160 for x in t]
    stream = {"t": t, "power": power, "hr": [120 + p // 10 for p in power]}
    # nur die erste kurze Runde trägt einen Workout-Schritt – zu wenig, das Workout lief nicht auf der Uhr mit
    ride_laps = [{"duration": 30, "distance": 0, "power": 200, "hr": 130, "kind": "warmup", "step": 0},
                 {"duration": 570, "distance": 0, "power": 205, "hr": 140}]
    res = laps.build({"id": "garmin:2", "sport": "ride", "metrics": {}}, ride_laps, stream, plan, RUN_SETTINGS)
    assert res["source"] == "plan"
    intervals = [s for s in res["segments"] if s["kind"] == "interval"]
    assert [s["power"] for s in intervals] == [280, 280] and [s["rep"] for s in intervals] == ["1/2", "2/2"]
    assert intervals[0]["target"] == {"type": "power", "low": 270, "high": 285} and intervals[0]["in_target"]
    assert res["intervals"][0]["in_target"] == 2


def test_swim_sets_of_equal_length_are_grouped():
    swim_laps = [lap(None, None, 90, 100, 130), lap("rest", None, 20, 0, 120), lap(None, None, 92, 100, 132),
                 lap("rest", None, 20, 0, 121), lap(None, None, 400, 400, 140)]
    res = laps.build({"id": "garmin:3", "sport": "swim", "metrics": {}}, swim_laps, None, None, RUN_SETTINGS)
    assert res["source"] == "laps" and [s.get("rep") for s in res["segments"]] == ["1/2", None, "2/2", None, None]
    assert res["intervals"][0]["count"] == 2 and res["intervals"][0]["avg_distance"] == 100


def test_garmin_laps_and_stream_are_parsed():
    raw = {"lapDTOs": [
        {"startTimeGMT": "2026-10-31T11:49:10.0", "duration": 331.4, "distance": 1000, "averageSpeed": 3.02,
         "averageHR": 150, "maxHR": 164, "intensityType": "WARMUP", "wktStepIndex": 0, "averageRunCadence": 170},
        {"startTimeGMT": "2026-10-31T11:54:53.0", "duration": 20, "distance": 88, "averageSpeed": 4.4,
         "averageHR": 163, "intensityType": "ACTIVE", "wktStepIndex": 1},
    ]}
    parsed = garmin.parse_laps(raw, "run")
    assert parsed[1]["start"] == 343 and parsed[1]["kind"] == "interval" and parsed[0]["cadence"] == 170
    swim = garmin.parse_laps({"lapDTOs": [{"startTimeGMT": "2026-11-24T06:00:00.0", "duration": 8, "distance": 0},
                                          {"startTimeGMT": "2026-11-24T06:00:08.0", "duration": 87, "distance": 75,
                                           "averageSpeed": 0.87, "averageSWOLF": 40,
                                           "lengthDTOs": [{"swimStroke": "FREESTYLE"}] * 3}]}, "swim")
    assert swim[0]["kind"] == "rest" and swim[1]["stroke"] == "Kraul" and swim[1]["swolf"] == 40
    stream = garmin.parse_stream({"metricDescriptors": [{"key": "sumDuration", "metricsIndex": 0},
                                                         {"key": "directPower", "metricsIndex": 1},
                                                         {"key": "directHeartRate", "metricsIndex": 2}],
                                  "activityDetailMetrics": [{"metrics": [0.0, 150.0, 110.0]}, {"metrics": [1.0, 152.0, None]}]})
    assert stream == {"t": [0.0, 1.0], "power": [150.0, 152.0], "hr": [110.0, None]}
