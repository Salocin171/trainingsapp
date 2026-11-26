from datetime import date, timedelta
from xml.etree import ElementTree

import pytest

from app import db, nutrition, periodization, recommend, templates, volume
from app.load import compute_series
from app.sync import garmin, intervals, zwift
from app.workouts import estimate_tss, repeat, step, total_duration

# Testdaten: erfundener Wettkampf am 27.6.2027, 12-h-Wochen
SETTINGS = {**db.DEFAULT_SETTINGS, "goal_name": "Ironman Kuckuckshausen", "goal_date": "2027-06-27", "week_hours": 12,
            "setup_done": True}


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


def test_duration_and_tss(intervals_workout):
    assert total_duration(intervals_workout["steps"]) == 60 * 60
    # Eine Stunde konstant an der FTP = 100 TSS
    assert estimate_tss({"sport": "ride", "steps": [step("steady", 60, 100)]}) == 100


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


def test_build_for_tss_hits_target():
    w = templates.build_for_tss("endurance", "ride", 70)
    assert abs(estimate_tss(w) - 70) < 10


def test_load_series_rises_with_training():
    start = date(2026, 1, 1)
    tss = {(start + timedelta(days=i)).isoformat(): 80 for i in range(60)}
    series = compute_series(tss, start, start + timedelta(days=59))
    assert series[-1]["ctl"] > 40 and series[-1]["atl"] > series[-1]["ctl"] * 0.9


def _kinds(days, iso=None):
    return [d["kind"] for d in days if iso is None or d["date"] == iso]


def test_recommendations_respect_fatigue_and_pattern():
    today = date(2026, 10, 26)  # Montag → Ruhetag + Dehnen laut Standardmuster
    days = recommend.plan_days(SETTINGS, today, {"ctl": 50, "atl": 95}, [], [], {}, 7)
    assert _kinds(days, "2026-10-26") == ["rest", "mobility"]
    # Dienstag ist "hart", aber TSB ist stark negativ → keine harte Einheit
    assert not any(templates.is_hard(k) for k in _kinds(days, "2026-10-27"))


def test_multiple_sessions_per_day():
    today = date(2026, 11, 3)  # Dienstag: Rad hart + Stabi
    days = recommend.plan_days(SETTINGS, today, {"ctl": 50, "atl": 45}, [], [], {}, 1)
    assert [d["sport"] for d in days] == ["ride", "strength"]
    assert templates.is_hard(days[0]["kind"])


def test_recovery_week_removes_intensity():
    # 4er-Rhythmus, rückwärts vom Rennen gezählt: 26.10.2026 ist eine Entlastungswoche
    info = periodization.week_info(SETTINGS, date(2026, 10, 26))
    assert info["recovery"] and info["block"] == "base"
    days = recommend.plan_days(SETTINGS, date(2026, 10, 27), {"ctl": 50, "atl": 45}, [], [], {}, 1)
    assert not any(templates.is_hard(k) for k in _kinds(days))


def test_ironman_blocks_and_heat():
    week = lambda d: periodization.week_info(SETTINGS, date.fromisoformat(d))  # noqa: E731
    assert week("2026-12-21")["block"] == "build1"
    assert week("2027-04-12")["block"] == "peak"
    assert week("2027-06-07")["block"] == "taper"
    assert week("2027-06-21")["race_week"]
    assert not week("2027-05-10")["heat"] and week("2027-05-17")["heat"]  # 6 Wochen vorher
    assert week("2027-07-05")["block"] == "transition"
    # Die letzte Woche vor dem Tapering ist immer eine Belastungswoche, davor jede 4. Entlastung
    assert not week("2027-05-31")["recovery"] and week("2027-05-10")["recovery"]


def test_heat_sessions_are_easy_ride_or_run():
    days = recommend.plan_days(SETTINGS, date(2027, 5, 24), {"ctl": 70, "atl": 65}, [], [], {}, 7)
    heat = [d for d in days if d.get("heat")]
    assert 0 < len(heat) <= periodization.week_info(SETTINGS, date(2027, 5, 24))["heat_sessions"]
    assert all(d["sport"] in ("ride", "run") and d["kind"] in ("endurance", "recovery") for d in heat)


def test_brick_run_after_long_ride_in_peak():
    days = recommend.plan_days(SETTINGS, date(2027, 5, 29), {"ctl": 70, "atl": 65}, [], [], {}, 1)
    assert _kinds(days)[-1] == "brick"


def test_taper_before_goal():
    settings = {**SETTINGS, "goal_date": "2026-11-01", "goal_name": "Rennen"}
    days = recommend.plan_days(settings, date(2026, 10, 29), {"ctl": 60, "atl": 60}, [], [], {}, 4)
    assert _kinds(days, "2026-10-30") == ["rest"]       # 2 Tage vorher
    assert _kinds(days, "2026-10-31") == ["openers"]    # Vortag: nur kurz aktivieren
    assert _kinds(days)[-1] == "race"


def test_planned_workouts_fill_their_slot():
    today = date(2026, 11, 3)
    planned = [{"date": today.isoformat(), "sport": "ride", "steps": [step("steady", 60, 70)]}]
    days = recommend.plan_days(SETTINGS, today, {"ctl": 50, "atl": 45}, planned, [], {}, 1)
    assert [d["sport"] for d in days] == ["strength"]  # Rad ist schon geplant, Stabi fehlt noch


def test_suggestions_match_week_hours():
    monday = date(2026, 11, 2)
    days = recommend.plan_days(SETTINGS, monday, {"ctl": 50, "atl": 45}, [], [], {}, 7)
    hours = sum(total_duration(d["workout"]["steps"]) for d in days
                if d.get("workout") and d["sport"] in templates.ENDURANCE_SPORTS) / 3600
    target = periodization.week_info(SETTINGS, monday)["target_hours"]
    assert abs(hours - target) / target < 0.25


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


def test_week_hours_and_goals():
    today = date(2026, 11, 4)
    activities = [
        {"date": "2026-11-02", "sport": "ride", "duration": 7200, "distance": 60000, "tss": 100},
        {"date": "2026-11-03", "sport": "strength", "duration": 1800, "distance": 0, "tss": 20},
    ]
    planned = [{"date": "2026-11-06", "sport": "run", "steps": [step("steady", 60, 75)]}]
    week = next(w for w in volume.weeks(SETTINGS, activities, planned, today) if w["current"])
    assert (week["done_hours"], week["planned_hours"], week["extra_hours"]) == (2.0, 1.0, 0.5)
    goal = {"sport": "ride", "metric": "km", "period": "month", "target": 300}
    progress = volume.goal_progress(goal, activities, planned, today)
    assert progress["value"] == 60 and progress["pct"] == 20


def test_old_settings_are_migrated(tmp_path):
    db.set_db_path(tmp_path / "old.db")
    db.save_settings({"week_pattern": {d: {"type": "hard", "sport": "run"} for d in recommend.WEEKDAYS}})
    with db.connect() as c:
        c.execute("REPLACE INTO settings(key, value) VALUES ('lthr', '180')")
    s = db.get_settings()
    assert s["lthr_run"] == s["lthr_ride"] == 180
    assert s["week_pattern"]["mon"] == [{"type": "hard", "sport": "run"}]


def test_db_roundtrip(tmp_path):
    db.set_db_path(tmp_path / "t.db")
    saved = db.save_workout({"date": "2026-11-01", "name": "Test", "steps": []})
    assert db.get_workout(saved["id"])["name"] == "Test"
    assert db.save_settings({"ftp": 280})["ftp"] == 280


def test_plan_import_example_file():
    import json
    from pathlib import Path
    from app import plan_import

    plan = json.loads(Path("app/static/plan-example.json").read_text())
    workouts, first, last = plan_import.parse(plan, date(2026, 10, 23))
    assert first == date(2026, 10, 26) and last == date(2026, 11, 22)  # nächster Montag + 4 Wochen
    assert len({w["date"] for w in workouts}) == 28
    tue = [w for w in workouts if w["date"] == "2026-10-27"]
    assert [w["sport"] for w in tue] == ["ride", "strength"]
    assert tue[0]["steps"][1] == repeat(3, step("interval", 12, 88, 93), step("recovery", 5, 50, 55))
    swim = next(w for w in workouts if w["name"] == "CSS 8x200")
    assert swim["steps"][1]["steps"][1]["duration"] == 20


def test_plan_import_days_dates_and_errors():
    from app import plan_import

    plan = {"start": "2026-11-04", "weeks": [{"week": 2, "days": {"Mittwoch": {"sport": "run", "template": "endurance"}}}],
            "workouts": [{"date": "2026-12-24", "sport": "swim", "steps": [{"minutes": 30, "low": 80}]}]}
    workouts, _, _ = plan_import.parse(plan, date(2026, 10, 23))
    assert [w["date"] for w in workouts] == ["2026-11-11", "2026-12-24"]  # Start wird auf Montag gesetzt
    assert workouts[1]["steps"] == [step("steady", 30, 80, 80)]
    for bad, message in [
        ({"weeks": [{"days": {"xyz": []}}]}, "unbekannter Tag"),
        ({"weeks": [{"days": {"mon": [{"sport": "rudern", "template": "endurance"}]}}]}, "unbekannter Sport"),
        ({"weeks": [{"days": {"mon": [{"sport": "run", "steps": [{"kind": "interval", "low": 90}]}]}}]}, "Dauer fehlt"),
        ({"weeks": []}, "Keine Workouts"),
    ]:
        with pytest.raises(plan_import.PlanError, match=message):
            plan_import.parse(bad, date(2026, 10, 23))


def test_plan_import_api_replaces_planned(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    db.set_db_path(tmp_path / "plan.db")
    db.save_workout({"date": "2026-11-03", "sport": "ride", "name": "Alt", "steps": [], "status": "planned"})
    db.save_workout({"date": "2026-11-03", "sport": "run", "name": "Erledigt", "steps": [], "status": "done"})
    client = TestClient(app)
    body = {"plan": {"weeks": [{"days": {"tue": [{"sport": "swim", "template": "endurance", "minutes": 45}]}}]},
            "start": "2026-11-02", "replace": True}
    preview = client.post("/api/plan/preview", json=body).json()
    assert preview["existing"] == 1 and preview["workouts"][0]["duration"] == 45 * 60
    res = client.post("/api/plan/import", json=body).json()
    assert (res["created"], res["removed"]) == (1, 1)
    names = [w["name"] for w in db.list_workouts("2026-11-03", "2026-11-03")]
    assert sorted(names) == ["Erledigt", "Grundlage"]
    assert client.post("/api/plan/preview", json={"plan": {"weeks": []}}).status_code == 400


def test_compliance_colors():
    from app import compliance

    plan = lambda i, d, sport, minutes: {"id": i, "date": d, "sport": sport, "steps": [step("steady", minutes, 70)]}  # noqa: E731
    workouts = [plan(1, "2026-11-02", "ride", 60), plan(2, "2026-11-03", "run", 60),
                plan(3, "2026-11-04", "swim", 60), plan(4, "2026-11-06", "run", 60)]
    activities = [
        {"id": "a1", "date": "2026-11-02", "sport": "ride", "duration": 3600, "tss": 50},   # Plan-TSS 49 → grün
        {"id": "a2", "date": "2026-11-03", "sport": "run", "duration": 1500, "tss": 0},     # 42 % Dauer → orange
        {"id": "a3", "date": "2026-11-04", "sport": "ride", "duration": 1800, "tss": 30},   # ungeplant
    ]
    rating, unplanned, links = compliance.evaluate(workouts, activities, date(2026, 11, 5))
    assert rating[1]["color"] == "green" and rating[1]["match"] == "same" and links["a1"]["workout_id"] == 1
    assert rating[2]["color"] == "orange" and rating[2]["match"] == "different" and links["a2"]["match"] == "different"
    assert rating[3]["color"] == "red"          # Schwimmen verpasst
    assert 4 not in rating                      # Zukunft: noch keine Bewertung
    assert unplanned == {"a3"}
    assert [compliance.color(p) for p in (79, 80, 120, 121, 151)] == ["yellow", "green", "green", "yellow", "orange"]


def _track_session():
    """5×1000 m wie im echten Plan: rund eine Stunde, davon 20 min an der Schwelle."""
    return {"id": 1, "date": "2026-10-31", "sport": "run", "name": "Bahn 5×1000 m Schwelle", "status": "planned", "steps": [
        step("warmup", 15, 70, 78), repeat(5, step("interval", 4, 99, 101), step("recovery", 2.5, 60, 70)), step("cooldown", 10, 65, 75)]}


def test_matching_recognizes_rough_match_but_not_a_different_session():
    from app import compliance

    today, settings = date(2026, 10, 31), {"lthr": 185, "ftp": 351}
    run = lambda minutes, zones, name="Kuckuckshausen Laufen", **kw: {  # noqa: E731
        "id": "a", "date": "2026-10-31", "sport": "run", "name": name, "duration": minutes * 60, "tss": 60,
        "metrics": {"hr_zones": zones, "max_hr": 165}, **kw}

    def judge(workout, activity):
        rating = compliance.evaluate([workout], [activity], today, settings)[0][1]
        return rating["match"], rating["reason"]

    assert judge(_track_session(), run(30, [100, 1700, 0, 0, 0])) == ("different", "30 statt 58 min")   # kurz und locker
    assert judge(_track_session(), run(60, [300, 3300, 0, 0, 0])) == ("different", "keine harte Belastung erkennbar")
    assert judge(_track_session(), run(60, [300, 2200, 700, 400, 0]))[0] == "same"                      # lief wirklich hart
    assert judge(_track_session(), run(60, []))[0] == "same"                                            # ohne Puls kein Gegenbeweis
    assert judge(_track_session(), run(31, [100, 1700, 0, 0, 0], name="Bahn 5x1000 Schwelle"))[0] == "same"  # abgebrochen
    easy = {"id": 1, "date": "2026-10-31", "sport": "run", "name": "Locker 30", "steps": [step("steady", 30, 70)]}
    assert judge(easy, run(31, [99, 1419, 353, 0, 0]))[0] == "same"
    assert judge(easy, run(30, [100, 900, 300, 500, 0])) == ("different", "deutlich härter als geplant")
    short_reps = {"id": 1, "date": "2026-10-31", "sport": "run", "name": "Steigerungen",
                  "steps": [repeat(10, step("interval", 0.5, 105), step("recovery", 1.5, 65))]}
    assert judge(short_reps, {**run(20, [100, 1100, 0, 0, 0]), "metrics": {"hr_zones": [100, 1100, 0, 0, 0], "max_hr": 175}})[0] == "same"


def test_matching_pairs_several_sessions_and_pieces():
    from app import compliance

    today = date(2026, 10, 31)
    plan = lambda i, minutes, name: {"id": i, "date": "2026-10-30", "sport": "ride", "name": name, "steps": [step("steady", minutes, 70)]}  # noqa: E731
    ride = lambda i, minutes, name="Radfahren": {"id": i, "date": "2026-10-30", "sport": "ride", "name": name, "duration": minutes * 60, "tss": 40}  # noqa: E731
    # zwei Fahrten am Tag: jede bekommt die passende, nicht beide dieselbe
    _, unplanned, links = compliance.evaluate([plan(1, 30, "A"), plan(2, 120, "B")], [ride("x", 118), ride("y", 32)], today)
    assert links["x"]["workout_id"] == 2 and links["y"]["workout_id"] == 1 and not unplanned
    # unterbrochene Aufzeichnung zählt zusammen
    rating, unplanned, links = compliance.evaluate([plan(1, 90, "A")], [ride("x", 60), ride("y", 30)], today)
    assert rating[1]["pct"] == 100 and len(links) == 2 and not unplanned
    # zusätzliche Einheit bleibt ungeplant
    _, unplanned, _ = compliance.evaluate([plan(1, 60, "A")], [ride("x", 60), ride("y", 60)], today)
    assert len(unplanned) == 1


def test_matching_manual_link_overrides_detection():
    from app import compliance

    today = date(2026, 10, 31)
    activity = {"id": "a", "date": "2026-10-31", "sport": "run", "name": "Lauf", "duration": 1800, "tss": 30, "metrics": {}}
    forced = compliance.evaluate([_track_session()], [{**activity, "feedback": {"plan_link": 1}}], today)
    assert forced[0][1]["match"] == "same" and not forced[1]
    none = compliance.evaluate([_track_session()], [{**activity, "feedback": {"plan_link": 0}}], today)
    assert 1 not in none[0] and none[1] == {"a"}


def test_matched_workout_is_no_longer_counted_as_planned(tmp_path):
    from fastapi.testclient import TestClient
    from app import main

    db.set_db_path(tmp_path / "match.db")
    today = date.today().isoformat()
    w = db.save_workout({"date": today, "name": "Locker", "sport": "run", "steps": [step("steady", 60, 70)], "status": "planned"})
    db.upsert_activities([{"id": "a", "date": today, "sport": "run", "name": "Lauf", "duration": 3600, "tss": 50,
                         "distance": 10000, "metrics": {}}])
    client = TestClient(main.app)
    week = [x for x in client.get("/api/weeks").json() if x["current"]][0]
    assert week["done_hours"] == 1 and week["planned_hours"] == 0

    # Zuordnung übersteht das Speichern von Feedback; "automatisch" entfernt sie wieder
    client.put("/api/activities/a/plan", json={"workout_id": 0})
    client.put("/api/activities/a/feedback", json={"rpe": 4})
    assert db.get_feedback("a") == {"plan_link": 0, "rpe": 4}
    week = [x for x in client.get("/api/weeks").json() if x["current"]][0]
    assert week["planned_hours"] == 1
    client.put("/api/activities/a/plan", json={"workout_id": None})
    assert db.get_feedback("a") == {"rpe": 4}
    assert client.get(f"/api/calendar?start={today}&end={today}").json()["activities"][0]["plan"] == {"workout_id": w["id"], "match": "same"}


def test_feedback_rules():
    from app import feedback

    today = date(2026, 11, 5)
    easy_but_hard = {"date": "2026-11-04", "sport": "run", "rpe": 8, "feel": 3, "easy": True, "hard": False, "label": "GA"}
    fb = feedback.evaluate([easy_but_hard], tsb=0, today=today)
    assert fb["warnings"] and fb["easy_until"] == "2026-11-06"
    # Vorschlag für morgen (Do, hart laut Muster) wird entschärft
    days = recommend.plan_days(SETTINGS, today, {"ctl": 50, "atl": 45}, [], [], {}, 2, fb)
    assert not any(templates.is_hard(d["kind"]) for d in days)

    tired = [{**easy_but_hard, "date": f"2026-11-0{i}", "rpe": 7, "easy": False, "feel": 2} for i in (3, 4, 5)]
    fb = feedback.evaluate(tired, tsb=-5, today=today)
    assert fb["reduce_until"] == "2026-11-06"

    too_easy = [{"date": d, "sport": "ride", "rpe": 3, "feel": 4, "easy": False, "hard": True, "label": "VO2"}
                for d in ("2026-10-20", "2026-10-28")]
    assert "zu niedrig" in feedback.evaluate(too_easy, tsb=0, today=today)["hints"][0]


def test_b_race_taper_and_recovery():
    races = [{"name": "70.3 Kraichgau", "date": "2026-11-08", "priority": "B", "race_type": "half"}]
    days = recommend.plan_days(SETTINGS, date(2026, 11, 5), {"ctl": 60, "atl": 55}, [], [], {}, 7, None, races)
    by_day = lambda iso: [d for d in days if d["date"] == iso]  # noqa: E731
    assert [d["kind"] for d in by_day("2026-11-08")] == ["race"]
    assert [d["kind"] for d in by_day("2026-11-07")] == ["openers"]            # Vortag: nur Aktivierung
    assert not any(templates.is_hard(d["kind"]) for d in days)                 # Mini-Taper + Erholung
    assert all(d["kind"] == "recovery" for d in by_day("2026-11-09") if d.get("sport") in ("swim", "ride", "run"))
    assert not any(d.get("sport") == "strength" for d in by_day("2026-11-06") + by_day("2026-11-09"))


def test_ctl_plan_and_ramp_risk():
    assert periodization.ramp_risk(40, 3) == "low" and periodization.ramp_risk(40, 7) == "high"
    assert periodization.ramp_risk(85, 6) == "medium"
    plan = periodization.ctl_plan({**SETTINGS, "target_ctl": 105}, date(2026, 10, 23), 85)
    assert plan["taper_start"] == "2027-06-07" and plan["risk"] == "low" and 0 < plan["ramp"] < 1
    assert periodization.ctl_plan({**SETTINGS, "target_ctl": 0}, date(2026, 10, 23), 85) is None


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


def test_mcp_server_tools(tmp_path, monkeypatch):
    """MCP-Tools gegen die echte API (TestClient + temporäre DB) statt gegen die laufende App."""
    import asyncio
    import json
    from fastapi.testclient import TestClient
    from app import mcp_server
    from app.main import app

    db.set_db_path(tmp_path / "mcp.db")
    client = TestClient(app)

    def fake_api(method, path, text=False, **kwargs):
        r = client.request(method, path, **kwargs)
        if r.status_code >= 400:
            raise RuntimeError(r.json().get("detail"))
        return r.text if text else r.json()

    monkeypatch.setattr(mcp_server, "_api", fake_api)
    call = lambda name, args: json.loads(asyncio.run(mcp_server.server.call_tool(name, args)).content[0].text)  # noqa: E731

    tools = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert {"get_status", "get_calendar", "create_workout", "import_plan", "set_activity_feedback"} <= tools

    created = call("create_workout", {"date": "2027-03-02", "sport": "ride", "name": "Schwelle 4x8", "steps": [
        {"kind": "warmup", "minutes": 15, "low": 50, "high": 75},
        {"repeat": 4, "steps": [{"kind": "interval", "minutes": 8, "low": 97, "high": 102},
                                {"kind": "recovery", "minutes": 4, "low": 50, "high": 55}]}]})
    wid = created["workout"]["id"]
    assert created["workout"]["minutes"] == 15 + 4 * 12
    assert call("update_workout", {"workout_id": wid, "rpe": 7, "note": "zäh"})["workout"]["rpe"] == 7
    assert [w["id"] for w in call("get_calendar", {"start": "2027-03-01", "end": "2027-03-07"})["workouts"]] == [wid]
    assert call("create_workout", {"date": "2027-03-03", "sport": "swim", "template": "threshold", "minutes": 50})["workout"]["sport"] == "swim"
    call("update_workout", {"workout_id": wid, "circuit": {"rounds": 3, "exercises": ["Plank"]}})
    assert db.get_workout(wid)["circuit"]["rounds"] == 3
    call("delete_workout", {"workout_id": wid})
    assert wid not in [w["id"] for w in call("get_calendar", {"start": "2027-03-01", "end": "2027-03-07"})["workouts"]]
    preview = call("import_plan", {"plan": {"weeks": [{"days": {
        "mon": [{"sport": "run", "template": "endurance", "pace": "5:00"}],
        "tue": [{"sport": "ride", "name": "VO2", "time": "6:30", "steps": "w15@55-75, 5x(i4@110-118, r4@50), c10@50"}]}}]},
        "start": "2027-03-08"})
    assert preview["start"] == "2027-03-08" and preview["warnings"] == ["Woche 1 Mo, Workout 1: Feld 'pace' unbekannt – ignoriert"]
    assert preview["weeks"]["KW 10"]["workouts"][1].startswith("03-09 ride 06:30 · VO2 65′")
    res = call("import_plan", {"preview_id": preview["preview_id"]})  # Plan nicht erneut senden
    assert res["created"] == 2 and db.list_workouts("2027-03-09", "2027-03-09")[0]["name"] == "06:30 · VO2"
    with pytest.raises(Exception):  # dieselbe Vorschau ist nur einmal importierbar
        call("import_plan", {"preview_id": preview["preview_id"]})
    brief = asyncio.run(mcp_server.server.call_tool("get_plan_brief", {"start": "2027-03-15", "weeks": 2})).content[0].text
    assert "Woche 2 (ab 22.03.)" in brief and "w=Einwärmen" in brief
    short = call("create_workout", {"date": "2027-03-04", "sport": "run", "steps": "w10@70-80, 3x(i6@97-101, r2@65), c10@65",
                                    "time": "18:00", "fueling": {"during": "0–30 g/h"}})
    assert short["workout"]["minutes"] == 44 and short["workout"]["name"].startswith("18:00 · ")
    assert call("update_settings", {"values": {"week_hours": 10}}) == {"week_hours": 10}


def test_cycle_start_and_taper_weeks():
    settings = {**SETTINGS, "cycle_start": "2026-11-09", "taper_weeks": 2}
    week = lambda d: periodization.week_info(settings, date.fromisoformat(d))  # noqa: E731
    recovery = [d for d in ("2026-11-30", "2026-12-28", "2027-01-25", "2027-02-22", "2027-03-22", "2027-04-19",
                            "2027-05-17") if week(d)["recovery"]]
    assert len(recovery) == 7
    assert week("2026-11-09")["cycle_week"] == 1 and not week("2026-11-23")["recovery"]
    assert week("2026-11-02")["cycle_week"] is None and week("2026-11-02")["cycle_starts"] == "2026-11-09"
    assert week("2027-06-07")["block"] == "peak" and week("2027-06-07")["cycle_week"] == 3  # direkt in den Taper
    assert week("2027-06-14")["block"] == "taper"
    assert periodization.next_recovery_week(settings, date(2026, 10, 23)) == "2026-11-30"


def test_season_plan_with_fixed_cycle_start():
    """Saisonplan Kuckuckshausen 2027: 4er-Blöcke ab 05.10., Block 8 ohne Entlastung, 2 Wochen Taper."""
    settings = {**SETTINGS, "goal_date": "2027-06-27", "race_type": "ironman", "recovery_every": 4,
                "cycle_start": "2026-10-05", "taper_weeks": 2}
    week = lambda d: periodization.week_info(settings, date.fromisoformat(d))  # noqa: E731
    mondays = [date(2026, 10, 5) + timedelta(weeks=i) for i in range(36)]
    assert [d.isoformat() for d in mondays if week(d.isoformat())["recovery"]] == [
        "2026-10-26", "2026-11-23", "2026-12-21", "2027-01-18", "2027-02-15", "2027-03-15", "2027-04-12", "2027-05-10"]
    assert week("2026-10-26")["cycle_week"] == 4
    assert [week(d)["cycle_week"] for d in ("2027-05-17", "2027-05-24", "2027-05-31", "2027-06-07")] == [1, 2, 3, 4]
    assert week("2027-06-07")["block"] != "taper" and not week("2027-06-07")["recovery"]
    assert week("2027-06-14")["block"] == "taper" and week("2027-06-21")["race_week"]
    assert periodization.next_recovery_week(settings, date(2026, 10, 31)) == "2026-11-23"
    assert periodization.next_recovery_week(settings, date(2027, 5, 17)) is None


def test_race_distances_recovery():
    from app import races

    marathon_b = races.profile({"race_type": "run_marathon", "priority": "B"})
    marathon_c = races.profile({"race_type": "run_marathon", "priority": "C"})
    assert marathon_b == {"taper": 7, "rest": 3, "recovery": 14, "no_run": 5}
    assert marathon_c["taper"] == 2 and marathon_c["recovery"] < marathon_b["recovery"]
    assert races.profile({"race_type": "run_5k", "priority": "B"})["recovery"] < marathon_b["recovery"]

    # Marathon am Sonntag: Mo–Fr danach Laufpause (Läufe werden zu lockerem Rad oder entfallen)
    race = [{"name": "Marathon", "date": "2027-03-14", "priority": "B", "race_type": "run_marathon"}]
    days = recommend.plan_days(SETTINGS, date(2027, 3, 15), {"ctl": 80, "atl": 70}, [], [], {}, 7, None, race)
    in_pause = [d for d in days if d["date"] <= "2027-03-19" and d.get("sport")]
    assert in_pause and not any(d["sport"] == "run" for d in in_pause)
    assert any("Laufpause" in r for d in days for r in d["reasons"])
    assert all(d["kind"] == "recovery" for d in days if d["date"] <= "2027-03-17" and d.get("sport") in ("swim", "ride", "run"))
    assert not any(templates.is_hard(d["kind"]) for d in days)
    assert [d["sport"] for d in days if d["date"] == "2027-03-21" and d.get("sport") == "run"] == ["run"]  # Tag 7: wieder laufen


def test_race_conflicts():
    from app import conflicts

    race = [{"name": "Marathon", "date": "2027-03-14", "priority": "B", "race_type": "run_marathon"}]
    w = lambda i, d, sport, kind, minutes: {"id": i, "date": d, "status": "planned", "name": f"{kind} {sport}",  # noqa: E731
                                             **templates.build(kind, sport, minutes)}
    plan = [
        w(1, "2027-03-13", "ride", "threshold", 60),   # Vortag hart → Aktivierung
        w(2, "2027-03-12", "run", "endurance", 90),    # 2 Tage vorher zu lang → kürzen
        w(3, "2027-03-10", "ride", "sweetspot", 80),   # 4 Tage vorher hart → im langen Taper noch ok
        w(4, "2027-03-11", "strength", "stabi", 40),   # Stabi im Taper → entfernen
        w(5, "2027-03-14", "swim", "endurance", 40),   # Renntag → entfernen
        w(6, "2027-03-16", "run", "endurance", 45),    # Laufpause → Rad
        w(7, "2027-03-20", "ride", "vo2max", 60),      # Erholung → keine Intensität
        w(8, "2027-03-30", "run", "threshold", 60),    # nach der Erholung → ok
    ]
    found = {c["workout_id"]: c for c in conflicts.check(plan, race, date(2027, 3, 1))}
    assert sorted(found) == [1, 2, 4, 5, 6, 7]
    assert found[1]["proposal"]["template"] == "openers"
    assert found[2]["proposal"]["template"] == "recovery" and total_duration(found[2]["proposal"]["steps"]) <= 60 * 60
    assert found[4]["action"] == found[5]["action"] == "delete"
    assert found[6]["proposal"]["sport"] == "ride" and found[6]["phase"] == "Laufpause"
    assert found[7]["proposal"]["template"] == "endurance"
    assert "Marathon" in found[7]["proposal"]["description"]
    assert conflicts.check(plan, race, date(2027, 3, 15))[0]["workout_id"] == 6  # Vergangenes wird nicht geprüft


def test_conflicts_api_apply(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app

    db.set_db_path(tmp_path / "conf.db")
    db.save_settings({"goal_date": "2027-06-27"})
    db.save_race({"name": "Marathon", "date": "2027-03-14", "priority": "B", "race_type": "run_marathon"})
    hard = db.save_workout({"date": "2027-03-13", "status": "planned", **templates.build("threshold", "ride", 60)})
    stabi = db.save_workout({"date": "2027-03-11", "status": "planned", **templates.build("stabi", "strength", 40)})
    client = TestClient(app)
    listed = client.get("/api/conflicts").json()
    assert {c["workout_id"] for c in listed} == {hard["id"], stabi["id"]}
    cal = client.get("/api/calendar", params={"start": "2027-03-09", "end": "2027-03-15"}).json()
    assert all(w["conflict"] for w in cal["workouts"])
    res = client.post("/api/conflicts/apply", json={"workout_ids": [hard["id"], stabi["id"]]}).json()
    assert len(res["applied"]) == 2 and not res["errors"]
    assert db.get_workout(hard["id"])["template"] == "openers" and db.get_workout(stabi["id"]) is None
    assert client.get("/api/conflicts").json() == []


def test_mcp_conflict_tools(tmp_path, monkeypatch):
    import asyncio
    import json
    from fastapi.testclient import TestClient
    from app import mcp_server
    from app.main import app

    db.set_db_path(tmp_path / "mcpconf.db")
    db.save_race({"name": "10 km Silvesterlauf", "date": "2027-12-31", "priority": "C", "race_type": "run_10k"})
    w = db.save_workout({"date": "2027-12-30", "status": "planned", **templates.build("vo2max", "run", 50)})
    client = TestClient(app)
    monkeypatch.setattr(mcp_server, "_api", lambda m, p, **kw: client.request(m, p, **kw).json())
    call = lambda name, args: json.loads(asyncio.run(mcp_server.server.call_tool(name, args)).content[0].text)  # noqa: E731
    found = call("check_race_conflicts", {})  # eine Liste mit einem Eintrag kommt als einzelnes Objekt an
    assert (found if isinstance(found, dict) else found[0])["workout_id"] == w["id"]
    call("resolve_race_conflicts", {"workout_ids": [w["id"]]})
    assert db.get_workout(w["id"])["template"] == "endurance"


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


def test_bulk_sync_skips_done_and_already_synced(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.sync import TARGETS

    db.set_db_path(tmp_path / "bulk.db")
    sent = []
    monkeypatch.setitem(TARGETS, "calendar", type("Fake", (), {
        "push": staticmethod(lambda w, s: sent.append(w["name"]) or {"uid": w["name"]}),
        "remove": staticmethod(lambda w: None), "is_connected": staticmethod(lambda: True)}))
    today = date.today().isoformat()
    for name, extra in (("neu", {}), ("erledigt", {"status": "done"}), ("schon da", {"sync": {"calendar": {"uid": "x"}}})):
        db.save_workout({"date": today, "name": name, "sport": "run", "steps": [step("steady", 30, 75)], "status": "planned", **extra})
    res = TestClient(main.app).post("/api/sync/bulk", json={"target": "calendar"}).json()
    assert res == {"sent": 1, "errors": []} and sent == ["neu"]


def test_auto_sync_skips_targets_not_set_up(tmp_path, monkeypatch):
    """Auto-Sync an ein nicht eingerichtetes Ziel (z. B. intervals.icu ohne Schlüssel) wird still übersprungen."""
    from fastapi.testclient import TestClient
    from app import main
    from app.sync import TARGETS

    db.set_db_path(tmp_path / "auto.db")
    db.save_settings({"auto_sync": ["calendar", "intervals"]})
    sent = []
    monkeypatch.setitem(TARGETS, "calendar", type("Fake", (), {
        "push": staticmethod(lambda w, s: sent.append(w["name"]) or {"uid": "1"}),
        "remove": staticmethod(lambda w: None), "is_connected": staticmethod(lambda: True)}))
    monkeypatch.setattr(main, "sync_status", lambda: {"calendar": True, "intervals": False})
    res = TestClient(main.app).post("/api/workouts", json={"date": "2026-11-03", "name": "Lauf", "sport": "run"}).json()
    assert res["errors"] == {} and sent == ["Lauf"] and list(res["workout"]["sync"]) == ["calendar"]


# --- Ernährung vor/während/nach ------------------------------------------------

FUEL_SETTINGS = {**SETTINGS, "weight": 80, "goal_date": "2027-06-27"}


def _ride(name, minutes, pct, date_="2026-11-22", **extra):
    return {"date": date_, "sport": "ride", "name": name, "target": "power",
            "steps": [step("steady", minutes, pct)], **extra}


def test_nutrition_scales_with_weight_and_session():
    long_ride = _ride("Rad lang Z2", 210, 70)
    n = nutrition.plan(long_ride, FUEL_SETTINGS)
    assert n["kind"] == "long"
    assert n["phases"]["before"]["carbs"] == {"low": 160, "high": 240, "unit": "g", "per_kg": (2, 3)}
    assert (n["phases"]["during"]["carbs"]["low"], n["phases"]["during"]["carbs"]["high"]) == (90, 90)  # Grundlage
    # 12 Wochen vor dem Rennen: Darmtraining in Renndosis
    late = nutrition.plan({**long_ride, "date": "2027-04-20"}, FUEL_SETTINGS)
    assert (late["phases"]["during"]["carbs"]["low"], late["phases"]["during"]["carbs"]["high"]) == (100, 120)

    easy_run = {"date": "2026-11-24", "sport": "run", "name": "Lauf locker", "steps": [step("steady", 45, 75)]}
    assert nutrition.plan(easy_run, FUEL_SETTINGS)["phases"]["during"]["carbs"]["high"] == 0
    short_vo2 = _ride("VO2", 60, 70) | {"steps": [step("warmup", 15, 55, 70), repeat(5, step("interval", 4, 112),
                                                                                     step("recovery", 3, 50)),
                                                  step("cooldown", 10, 50)]}
    n = nutrition.plan(short_vo2, FUEL_SETTINGS)
    assert n["kind"] == "quality" and n["phases"]["during"]["carbs"]["high"] == 30
    assert n["phases"]["before"]["carbs"]["per_kg"] == (1, 2)


def test_nutrition_context_brick_early_start_and_fast_refuel():
    ride = _ride("Rad lang Z2", 180, 70, id=1)
    brick = {"id": 2, "date": "2026-11-22", "sport": "run", "name": "Koppellauf 5 km", "steps": [step("steady", 30, 80)]}
    n_ride = nutrition.plan(ride, FUEL_SETTINGS, [ride, brick])
    assert "Koppellauf" in n_ride["phases"]["after"]["hint"]
    n_brick = nutrition.plan(brick, FUEL_SETTINGS, [ride, brick])
    assert n_brick["kind"] == "brick" and n_brick["phases"]["before"]["carbs"] is None
    assert n_brick["phases"]["during"]["carbs"]["high"] == 90

    morning = _ride("07:00 · Rad Z2", 90, 68, id=3)
    evening = _ride("13:00 · Rad Sweet Spot", 90, 90, id=4)
    n = nutrition.plan(morning, FUEL_SETTINGS, [morning, evening])
    assert n["start"] == "07:00" and n["end"] == "08:30"
    assert n["phases"]["before"]["carbs"]["per_kg"] == (0.5, 1)          # früher Start
    assert n["phases"]["after"]["carbs"]["unit"] == "g/h"                # Qualität in < 8 h → schnell auffüllen
    assert n["phases"]["during"]["carbs"]["high"] == 90                  # locker vor harter Folgeeinheit


def test_nutrition_prefers_numbers_from_plan_text():
    desc = ("Z2.\n\nKH (80 kg):\n- Vorher: 0,5–1 g/kg (45–85 g) 60–90 min vorher.\n"
            "- Während: bis 90 min 60 g/h, danach 90 g/h.\n"
            "- Danach: Mahlzeit mit 85–130 g KH + 30–40 g Protein; Tagesziel 6–10 g/kg (510–850 g).")
    n = nutrition.plan(_ride("Rad", 150, 70, description=desc), FUEL_SETTINGS)
    ph = n["phases"]
    assert (ph["before"]["carbs"]["low"], ph["before"]["carbs"]["high"], ph["before"]["source"]) == (45, 85, "plan")
    assert (ph["during"]["carbs"]["low"], ph["during"]["carbs"]["high"]) == (60, 90)
    assert (ph["after"]["carbs"]["low"], ph["after"]["carbs"]["high"]) == (85, 130)
    assert (ph["after"]["protein"]["low"], ph["after"]["protein"]["high"]) == (30, 40)
    assert ph["during"]["plan_text"].startswith("bis 90 min") and ph["during"]["hint"] == ""
    assert n["day"]["per_kg"] == (6, 10) and n["day"]["source"] == "plan"


def test_nutrition_fluid_from_sweat_rate():
    ride = _ride("Rad", 120, 70)
    unknown = nutrition.plan(ride, FUEL_SETTINGS)
    assert unknown["phases"]["during"]["fluid"]["unit"] == "ml/h" and unknown["phases"]["after"]["fluid"] is None
    n = nutrition.plan(ride, {**FUEL_SETTINGS, "sweat_rate": 1.5})
    fluid = n["phases"]["during"]["fluid"]
    # 80 kg, 2 h: 2 % = 1,6 l → 1,5 − 0,8 = 0,7 l/h; 1 % → 1,1 l/h; nie mehr als die Schweißrate
    assert (fluid["low"], fluid["high"]) == (700, 1100)
    assert n["phases"]["after"]["fluid"]["low"] > 0


# --- Einrichtung für neue Nutzer ------------------------------------------------

def test_new_database_starts_setup_and_old_database_keeps_its_defaults(tmp_path):
    import sqlite3

    db.set_db_path(tmp_path / "neu.db")
    fresh = db.get_settings()
    assert fresh["setup_done"] is False and fresh["goal_date"] == "" and fresh["plant_based"] is False

    # Datenbank aus einer Version vor dem Einrichtungsdialog: gilt als eingerichtet, gespeicherte Werte bleiben
    old = tmp_path / "alt.db"
    with sqlite3.connect(old) as conn:
        conn.executescript(db.SCHEMA)
        conn.execute("INSERT INTO settings VALUES ('ftp', '300')")
    db.set_db_path(old)
    s = db.get_settings()
    assert s["ftp"] == 300 and s["setup_done"] is True
    with sqlite3.connect(old) as conn:
        assert conn.execute("SELECT value FROM settings WHERE key = 'setup_done'").fetchone()[0] == "true"


def test_setup_garmin_login_with_mfa(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config, main

    db.set_db_path(tmp_path / "setup.db")
    monkeypatch.setattr(config, "GARMIN_TOKEN_DIR", tmp_path / "tokens")
    calls = []

    class FakeGarmin:
        def __init__(self, email=None, password=None, return_on_mfa=False):
            calls.append(("init", email, return_on_mfa))
            self.client = type("C", (), {"dump": lambda _, path: calls.append(("dump", path))})()

        def login(self):
            return "needs_mfa", {"state": 1}

        def resume_login(self, state, code):
            calls.append(("mfa", state, code))
            return None, None

        def get_full_name(self):
            return "Freundin Test"

    import garminconnect
    monkeypatch.setattr(garminconnect, "Garmin", FakeGarmin)
    monkeypatch.setattr(garmin, "import_profile",
                        lambda: {"ftp": 230, "weight": 64.0, "css_garmin": {"css": 110, "at": "2026-11-01"}})
    client = TestClient(main.app)
    assert client.post("/api/setup/garmin", json={"email": "a@b.de", "password": "x"}).json() == {"mfa": True}
    res = client.post("/api/setup/garmin", json={"code": " 123456 "}).json()
    assert res["name"] == "Freundin Test" and res["profile"] == {
        "ftp": 230, "weight": 64.0, "css": 110, "css_garmin_seen": "2026-11-01"}
    assert ("mfa", {"state": 1}, "123456") in calls and ("dump", str(tmp_path / "tokens")) in calls
    # ohne wartende Anmeldung gibt es eine verständliche Meldung statt eines Absturzes
    assert "erneut" in client.post("/api/setup/garmin", json={"code": "1"}).json()["detail"]
    garmin._client = None


def test_plan_import_compact_steps_time_fueling_and_warnings():
    from app import plan_import as pi

    warnings = []
    plan = {"name": "KI", "notes": "x", "weeks": [{"week": 1, "days": {"tue": [
        {"sport": "swim", "name": "CSS", "time": "6.45", "steps": "w10@75-85; 8x(i3@97-101, r20s); c5@70-80",
         "fueling": {"during": "0–30 g/h", "day": "5–7 g/kg", "gels": 2}}]}}]}
    (w,), first, _ = pi.parse(plan, date(2026, 11, 21), warnings=warnings)
    assert first == date(2026, 11, 24) and w["name"] == "06:45 · CSS"
    assert total_duration(w["steps"]) == (10 + 8 * 3 + 5) * 60 + 8 * 20
    assert w["description"] == "KH:\n- Während: 0–30 g/h.\n- Danach: Tagesziel 5–7 g/kg."
    assert warnings == ["Plan: Feld 'notes' unbekannt – ignoriert",
                        "Woche 1 Di, Workout 1, fueling: Feld 'gels' unbekannt – ignoriert"]
    with pytest.raises(pi.PlanError, match="nicht verstanden"):
        pi.parse({"weeks": [{"days": {"mon": [{"sport": "run", "steps": "Z2 60 min"}]}}]}, date(2026, 11, 21))
    with pytest.raises(pi.PlanError, match="Uhrzeit"):
        pi.parse({"weeks": [{"days": {"mon": [{"sport": "run", "template": "endurance", "time": "25:00"}]}}]},
                 date(2026, 11, 21))


def test_plan_prompt_contains_targets_pattern_and_format():
    from app import plan_prompt

    settings = {**SETTINGS, "weight": 72, "cycle_start": "2026-11-02"}
    text = plan_prompt.build(settings, date(2026, 11, 23), 4,
                             [{"name": "Testlauf", "date": "2026-12-06", "priority": "C", "race_type": "run_10k"}],
                             ctl=55.4, past_hours=[6.5, 7.0])
    assert "Gewicht 72 kg" in text and "FTP 250 W" in text and "Fitness (CTL) aktuell 55" in text
    assert text.count("- Woche ") == 4 and "Entlastungswoche" in text and "Soll " in text
    assert "06.12.2026 Testlauf (C)" in text and "w=Einwärmen" in text and "Ernährung NICHT angeben" in text


ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:test
BEGIN:VEVENT
UID:vl1
SUMMARY:Vorlesung Geheim
DTSTART;TZID=Europe/Berlin:20261124T100000
DTEND;TZID=Europe/Berlin:20261124T120000
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=Europe/Berlin:20261208T100000
END:VEVENT
BEGIN:VEVENT
UID:vl2
DTSTART;TZID=Europe/Berlin:20261124T113000
DTEND;TZID=Europe/Berlin:20261124T130000
END:VEVENT
BEGIN:VEVENT
UID:frei
DTSTART;TZID=Europe/Berlin:20261125T080000
DTEND;TZID=Europe/Berlin:20261125T090000
TRANSP:TRANSPARENT
END:VEVENT
BEGIN:VEVENT
UID:reise
DTSTART;VALUE=DATE:20261202
DTEND;VALUE=DATE:20261204
END:VEVENT
BEGIN:VEVENT
UID:erinnerung
SUMMARY:Abgabe
DTSTART;VALUE=DATE:20261126
DTEND;VALUE=DATE:20261127
END:VEVENT
BEGIN:VEVENT
UID:nacht
DTSTART:20261127T220000Z
DTEND:20261128T010000Z
END:VEVENT
END:VCALENDAR
"""


def test_busy_times_from_ical():
    from app import availability

    busy = availability.busy_from_ics(ICS, date(2026, 11, 23), date(2026, 12, 20))
    assert busy[date(2026, 11, 24)] == [("10:00", "13:00")]          # überlappende Termine zusammengefasst
    assert busy[date(2026, 12, 1)] == [("10:00", "12:00")]           # Wiederholung
    assert date(2026, 12, 8) not in busy                              # Ausnahme (EXDATE)
    assert busy[date(2026, 12, 15)] == [("10:00", "12:00")]
    assert date(2026, 11, 25) not in busy                             # als „frei“ markiert
    assert busy[date(2026, 12, 2)] == busy[date(2026, 12, 3)] == ["ganztägig"] and date(2026, 12, 4) not in busy
    assert date(2026, 11, 26) not in busy                             # eintägige Erinnerung blockiert nicht
    assert busy[date(2026, 11, 27)] == [("23:00", "23:59")] and busy[date(2026, 11, 28)] == [("00:00", "02:00")]


def test_plan_prompt_without_own_pattern_uses_free_times():
    from app import plan_prompt

    busy = {date(2026, 11, 24): [("10:00", "13:00")], date(2026, 12, 2): ["ganztägig"], date(2027, 1, 5): ["ganztägig"]}
    text = plan_prompt.build(SETTINGS, date(2026, 11, 23), 2, [], busy=busy, notes="Schwimmbad nur Di früh",
                             default_pattern=db.DEFAULT_SETTINGS["week_pattern"])
    assert "Mein übliches Wochenmuster" not in text and "Kein festes Wochenmuster" in text
    assert "Schwimmbad nur Di früh" in text and "- Di 24.11.: 10:00–13:00" in text and "- Mi 02.12.: ganztägig" in text
    assert "05.01." not in text                                        # außerhalb des Blocks
    own = plan_prompt.build({**SETTINGS, "week_pattern": {"mon": [{"sport": "run", "type": "easy"}]}}, date(2026, 11, 23),
                            1, [], default_pattern=db.DEFAULT_SETTINGS["week_pattern"])
    assert "Mein übliches Wochenmuster" in own and "Mo: Laufen locker" in own and "Wann ich trainieren kann" not in own


def test_ef_series_skips_mixed_and_off_intensity_rides():
    from app import analysis

    def ride(day, np_, avg_power, hr, zones=(0, 3600, 0, 0, 0), **extra):
        return {"date": f"2026-11-{day:02d}", "sport": "ride", "name": f"R{day}", "duration": 7200,
                "metrics": {"np": np_, "avg_power": avg_power, "avg_hr": hr, "hr_zones": list(zones), **extra}}

    acts = [
        ride(1, 250, 248, 145),                                # gleichmäßige Grundlage → zählt
        ride(2, 300, 250, 148, zones=(0, 2500, 400, 700, 0)),  # 1 h Intervalle + 1 h locker → hohe NP, niedriger Puls
        ride(3, 280, 240, 135),                                # Kurzintervalle ohne Puls in Z4 → VI zu hoch
        ride(4, 160, 159, 125),                                # Ausrollen < 45 % FTP
        ride(5, 320, 318, 160),                                # Schwelle ≥ 80 % FTP
        ride(6, 250, 247, 140, anaerobic_te=2.1),              # Antritte laut Garmin
        ride(7, 250, 236, 140, indoor=True),                   # Rolle: VI 1,06 > 1,05
        ride(8, 240, 238, 142, event_type="race"),
    ]
    e = analysis.ef_series(acts, date(2026, 11, 25), ftp=385)["ride"]
    assert [p["name"] for p in e["points"]] == ["R1"]
    reasons = {x["name"]: x["reason"] for x in e["excluded"]}
    assert set(reasons) == {"R2", "R3", "R4", "R5", "R6", "R7", "R8"}
    assert "ungleichmäßig" in reasons["R3"] and "ungleichmäßig" in reasons["R7"]
    assert "zu locker" in reasons["R4"] and "zu intensiv" in reasons["R5"]
    assert "anaerob" in reasons["R6"] and reasons["R8"] == "Wettkampf"
    assert e["np_range"] == [173, 308] and e["ref_hr"] == 145


def test_ef_series_normalizes_to_reference_hr_and_detects_bricks():
    from app import analysis

    # gleiche Form: Puls = 80 + 0,25 × Watt → bei jedem Puls dieselbe Leistung beim Referenzpuls
    rides = [{"date": f"2026-11-{d:02d}", "sport": "ride", "name": "R", "duration": 5400,
              "metrics": {"np": w, "avg_power": w, "avg_hr": 80 + 0.25 * w, "hr_zones": [0, 3600, 0, 0, 0],
                          "start_time": f"2026-11-{d:02d} 08:00:00"}}
             for d, w in zip(range(1, 13), (200, 220, 240, 260, 280, 210, 230, 250, 270, 205, 245, 265))]
    run = {"date": "2026-11-05", "sport": "run", "name": "Koppel", "duration": 1800,
           "metrics": {"avg_hr": 150, "gap": 3.0, "hr_zones": [0, 1800, 0, 0, 0], "start_time": "2026-11-05 09:40:00"}}
    r = analysis.ef_series(rides + [run], date(2026, 11, 25), ftp=385)
    assert abs(r["ride"]["slope"] - 0.25) < 0.01
    at_ref = {p["at_ref"] for p in r["ride"]["points"]}
    assert max(at_ref) - min(at_ref) < 1                   # Intensität herausgerechnet
    assert r["run"]["excluded"][0]["reason"].startswith("Koppellauf")


def test_ef_series_scales_with_performance_level():
    """Halbe Watt bei halber FTP und gleichem Puls → gleiche Einheiten zählen, Steigung doppelt so steil."""
    from app import analysis

    def rides(factor):
        return [{"date": f"2026-11-{d:02d}", "sport": "ride", "name": f"R{d}", "duration": 5400,
                 "metrics": {"np": w * factor, "avg_power": w * factor, "avg_hr": hr, "hr_zones": [0, 3600, 0, 0, 0]}}
                for d, (w, hr) in enumerate(((200, 130), (230, 140), (260, 146), (215, 137), (245, 141)), start=1)]

    strong = analysis.ef_series(rides(1), date(2026, 11, 25), ftp=385)["ride"]
    weak = analysis.ef_series(rides(0.5), date(2026, 11, 25), ftp=192.5)["ride"]
    assert len(strong["points"]) == len(weak["points"]) == 5
    assert weak["slope"] == pytest.approx(2 * strong["slope"], abs=0.002)  # zu wenig Paare → Standard, skaliert mit FTP
    assert weak["slope"] == pytest.approx(110 / 192.5, abs=0.001)
    assert [p["at_ref"] for p in weak["points"]] == pytest.approx([p["at_ref"] / 2 for p in strong["points"]], abs=0.1)


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


def test_updater_detects_and_applies_new_commits(tmp_path, monkeypatch):
    import subprocess
    from app import config, updater

    def git(cwd, *args):
        subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                       capture_output=True)

    origin, upstream, local = tmp_path / "origin.git", tmp_path / "upstream", tmp_path / "local"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(upstream))
    (upstream / "app").mkdir()
    (upstream / "app" / "x.py").write_text("A = 1\n")
    git(upstream, "add", ".")
    git(upstream, "commit", "-q", "-m", "Erste Version")
    git(upstream, "push", "-q", "origin", "HEAD:main")
    git(tmp_path, "clone", "-q", str(origin), str(local))
    monkeypatch.setattr(config, "ROOT", local)

    assert updater.status(force=True)["available"] is False
    (upstream / "app" / "x.py").write_text("A = 2\n")
    git(upstream, "commit", "-qam", "Neue Funktion")
    git(upstream, "push", "-q", "origin", "HEAD:main")
    s = updater.status(force=True)
    assert s["available"] and s["behind"] == 1 and s["commits"] == ["Neue Funktion"]

    res = updater.apply()
    assert res["updated"] and res["restart_claude"] and (local / "app" / "x.py").read_text() == "A = 2\n"
    assert updater.status(force=True)["available"] is False

    monkeypatch.setattr(config, "ROOT", tmp_path / "zip-download")  # ohne .git: kein Button, Hinweis auf Update.command
    (tmp_path / "zip-download").mkdir()
    assert updater.status(force=True)["supported"] is False


def test_autostart_status_knows_the_folder(tmp_path, monkeypatch):
    import plistlib
    from app import autostart, config
    plist = tmp_path / "de.trainingsapp.plist"
    monkeypatch.setattr(autostart, "PLIST", plist)
    monkeypatch.setattr(autostart, "_service_pid", lambda: None)
    assert autostart.status()["installed"] is False
    plist.write_bytes(plistlib.dumps({"Label": "de.trainingsapp", "WorkingDirectory": str(tmp_path / "anderswo")}))
    s = autostart.status()
    assert s["installed"] and not s["this_folder"] and not s["active"]
    plist.write_bytes(plistlib.dumps({"Label": "de.trainingsapp", "WorkingDirectory": str(config.ROOT)}))
    assert autostart.status()["this_folder"]
