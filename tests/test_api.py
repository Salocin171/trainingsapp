"""HTTP-API gegen eine temporäre Datenbank (TestClient)."""
from datetime import date

from app import db, templates
from app.sync import garmin
from app.workouts import step


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
    from app import main, services
    from app.sync import TARGETS

    db.set_db_path(tmp_path / "auto.db")
    db.save_settings({"auto_sync": ["calendar", "intervals"]})
    sent = []
    monkeypatch.setitem(TARGETS, "calendar", type("Fake", (), {
        "push": staticmethod(lambda w, s: sent.append(w["name"]) or {"uid": "1"}),
        "remove": staticmethod(lambda w: None), "is_connected": staticmethod(lambda: True)}))
    monkeypatch.setattr(services, "connected", lambda settings=None: {"calendar": True, "intervals": False})
    res = TestClient(main.app).post("/api/workouts", json={"date": "2026-11-03", "name": "Lauf", "sport": "run"}).json()
    assert res["errors"] == {} and sent == ["Lauf"] and list(res["workout"]["sync"]) == ["calendar"]


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


def test_settings_are_validated():
    """PUT /api/settings speichert nur mitgeschickte Felder und lehnt Tippfehler, null und falsche Typen ab."""
    from fastapi.testclient import TestClient
    from app import main

    client = TestClient(main.app)
    saved = client.put("/api/settings", json={"ftp": 280, "week_hours": 11.5, "goal_date": "2027-06-27"}).json()
    assert saved["ftp"] == 280 and isinstance(saved["ftp"], int) and saved["week_hours"] == 11.5
    assert saved["max_hr"] == db.DEFAULT_SETTINGS["max_hr"]              # nicht mitgeschickt → unverändert
    for bad in ({"ftpp": 280}, {"ftp": None}, {"ftp": "viel"}, {"ftp": -5}, {"goal_date": "27.6.2027"},
                {"auto_sync": ["strava"]}, {"race_type": "sprint"}, {"week_pattern": {"mon": [{"type": "hard"}]}}):
        assert client.put("/api/settings", json=bad).status_code == 422, bad
    assert db.get_settings()["ftp"] == 280


def test_settings_model_matches_defaults():
    from app.schemas import SettingsIn

    assert set(SettingsIn.model_fields) == set(db.DEFAULT_SETTINGS)


def test_deleted_activity_is_not_imported_again(tmp_path):
    from fastapi.testclient import TestClient
    from app import main

    db.set_db_path(tmp_path / "delete.db")
    today = date.today().isoformat()
    double = [{"id": i, "date": today, "sport": "ride", "name": n, "duration": 3600, "tss": 60, "metrics": {}}
              for i, n in (("garmin:1", "Zwift"), ("garmin:2", "Rolle"))]
    db.upsert_activities(double)
    db.save_feedback("garmin:2", {"rpe": 5})
    db.set_cache("laps:garmin:2", "x", {"laps": []})
    client = TestClient(main.app)
    assert client.delete("/api/activities/garmin%3A2").json() == {"ok": True}
    assert [a["id"] for a in db.list_activities(today, today)] == ["garmin:1"]
    assert db.get_feedback("garmin:2") == {} and db.get_cache("laps:garmin:2") is None
    assert db.upsert_activities(double) == 1  # nächster Import holt sie nicht zurück
    assert [a["id"] for a in db.list_activities(today, today)] == ["garmin:1"]
    assert client.delete("/api/activities/garmin%3A2").status_code == 404
