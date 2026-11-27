"""Belastung (CTL/ATL), Periodisierung, Wochenstunden, Wettkämpfe und Konflikte."""
from datetime import date, timedelta

from app import periodization, recommend, templates, volume
from app.load import compute_series
from app.workouts import step, total_duration

from helpers import SETTINGS


def test_load_series_rises_with_training():
    start = date(2026, 1, 1)
    tss = {(start + timedelta(days=i)).isoformat(): 80 for i in range(60)}
    series = compute_series(tss, start, start + timedelta(days=59))
    assert series[-1]["ctl"] > 40 and series[-1]["atl"] > series[-1]["ctl"] * 0.9


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


def test_ctl_plan_and_ramp_risk():
    assert periodization.ramp_risk(40, 3) == "low" and periodization.ramp_risk(40, 7) == "high"
    assert periodization.ramp_risk(85, 6) == "medium"
    plan = periodization.ctl_plan({**SETTINGS, "target_ctl": 105}, date(2026, 10, 23), 85)
    assert plan["taper_start"] == "2027-06-07" and plan["risk"] == "low" and 0 < plan["ramp"] < 1
    assert periodization.ctl_plan({**SETTINGS, "target_ctl": 0}, date(2026, 10, 23), 85) is None


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


def test_calendar_weeks_mark_cycle_and_block_starts():
    settings = {**SETTINGS, "cycle_start": "2026-11-09", "recovery_every": 4, "taper_weeks": 2}
    weeks = periodization.calendar_weeks(settings, date(2026, 11, 4), date(2026, 12, 13))
    assert [w["week_start"] for w in weeks] == ["2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23", "2026-11-30",
                                                "2026-12-07"]
    assert weeks[0]["prelude"] and not weeks[0]["starts"]
    assert weeks[1]["starts"] and weeks[1]["cycle_week"] == 1 and not weeks[2]["starts"]
    assert weeks[4]["recovery"] and weeks[5]["starts"]
    block_change = periodization.calendar_weeks(settings, date(2027, 6, 14), date(2027, 6, 14))[0]
    assert block_change["block"] == "taper" and block_change["starts"]


def test_week_overview_shows_two_cycles():
    settings = {**SETTINGS, "cycle_start": "2026-11-02", "recovery_every": 4, "taper_weeks": 2}
    window = lambda d: periodization.cycle_window(settings, date.fromisoformat(d))  # noqa: E731
    assert window("2026-11-27") == (3, 4)   # kein voriger Zyklus (Vorlauf): laufender + nächster
    assert window("2026-12-21") == (7, 0)   # vorheriger + laufender, bis zur Entlastungswoche
    assert window("2026-12-28") == (4, 3)   # neuer Zyklus: der älteste fällt raus
    assert window("2027-06-21") == (4, 3)   # Tapering: kein Rhythmus, 8 Wochen rund um heute


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
