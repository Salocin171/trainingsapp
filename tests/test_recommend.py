"""Vorschläge (recommend) und Feedback-Regeln."""
from datetime import date

from app import periodization, recommend, templates
from app.workouts import step, total_duration

from helpers import SETTINGS


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


def test_own_spacing_rules_skip_hard_gap_check():
    today = date(2026, 11, 3)  # Dienstag: Rad hart, am Montag schon hartes Rad erledigt
    hard_ride = [{"date": "2026-11-02", "sport": "ride", "tss": 90, "duration": 3600}]
    state = {"ctl": 50, "atl": 45}
    default = recommend.plan_days(SETTINGS, today, state, [], hard_ride, {}, 1)
    assert not templates.is_hard(default[0]["kind"])
    own = recommend.plan_days({**SETTINGS, "own_spacing_rules": True}, today, state, [], hard_ride, {}, 1)
    assert templates.is_hard(own[0]["kind"])


def test_recovery_week_removes_intensity():
    # 4er-Rhythmus, rückwärts vom Rennen gezählt: 26.10.2026 ist eine Entlastungswoche
    info = periodization.week_info(SETTINGS, date(2026, 10, 26))
    assert info["recovery"] and info["block"] == "base"
    days = recommend.plan_days(SETTINGS, date(2026, 10, 27), {"ctl": 50, "atl": 45}, [], [], {}, 1)
    assert not any(templates.is_hard(k) for k in _kinds(days))


def test_heat_sessions_are_easy_ride_or_run():
    days = recommend.plan_days(SETTINGS, date(2027, 5, 24), {"ctl": 70, "atl": 65}, [], [], {}, 7)
    heat = [d for d in days if d.get("heat")]
    assert 0 < len(heat) <= periodization.week_info(SETTINGS, date(2027, 5, 24))["heat_sessions"]
    assert all(d["sport"] in ("ride", "run") and d["kind"] in ("endurance", "recovery") for d in heat)


def test_brick_run_after_long_ride_in_peak():
    days = recommend.plan_days(SETTINGS, date(2027, 5, 29), {"ctl": 70, "atl": 65}, [], [], {}, 1)
    assert _kinds(days)[-1] == "brick"


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


def test_taper_before_goal():
    settings = {**SETTINGS, "goal_date": "2026-11-01", "goal_name": "Rennen"}
    days = recommend.plan_days(settings, date(2026, 10, 29), {"ctl": 60, "atl": 60}, [], [], {}, 4)
    assert _kinds(days, "2026-10-30") == ["rest"]       # 2 Tage vorher
    assert _kinds(days, "2026-10-31") == ["openers"]    # Vortag: nur kurz aktivieren
    assert _kinds(days)[-1] == "race"
