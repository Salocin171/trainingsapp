"""Plan-Import, KI-Auftrag und freie Zeiten aus iCal."""
from datetime import date

import pytest

from app import db
from app.workouts import repeat, step, total_duration

from helpers import SETTINGS


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
