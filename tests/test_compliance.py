"""Plan gegen Ist: Farben und Zuordnung von Aktivitäten zu Workouts."""
from datetime import date

from app.workouts import repeat, step


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

    today, settings = date(2026, 10, 31), {"lthr_run": 185, "lthr_ride": 150, "ftp": 351}
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
    short_run = {**run(20, [100, 1100, 0, 0, 0]), "metrics": {"hr_zones": [100, 1100, 0, 0, 0], "max_hr": 175}}
    assert judge(short_reps, short_run)[0] == "same"                       # Max-Puls nahe LTHR Laufen
    settings = {"lthr_ride": 185, "ftp": 351}                              # nur Rad-Schwelle: zählt beim Laufen nicht
    assert judge(short_reps, short_run) == ("different", "keine harte Belastung erkennbar")


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
