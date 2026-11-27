"""Datenbank: Speichern, Migration älterer Datenbanken, Einrichtung."""

from app import db, recommend


def test_old_settings_are_migrated(tmp_path):
    db.set_db_path(tmp_path / "old.db")
    db.save_settings({"week_pattern": {d: {"type": "hard", "sport": "run"} for d in recommend.WEEKDAYS}})
    with db.connect() as c:
        c.execute("REPLACE INTO settings(key, value) VALUES ('lthr', '180')")
    s = db.get_settings()
    assert s["lthr_run"] == s["lthr_ride"] == 180 and "lthr" not in s
    assert s["week_pattern"]["mon"] == [{"type": "hard", "sport": "run"}]


def test_db_roundtrip(tmp_path):
    db.set_db_path(tmp_path / "t.db")
    saved = db.save_workout({"date": "2026-11-01", "name": "Test", "steps": []})
    assert db.get_workout(saved["id"])["name"] == "Test"
    assert db.save_settings({"ftp": 280})["ftp"] == 280


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


def test_schema_is_set_up_once_and_again_after_the_file_is_gone(tmp_path, monkeypatch):
    path = tmp_path / "einmal.db"
    db.set_db_path(path)
    calls = []
    original = db.init_db
    monkeypatch.setattr(db, "init_db", lambda: calls.append(1) or original())
    db.get_settings()
    db.save_workout({"date": "2026-11-01", "name": "A", "steps": []})
    db.list_workouts("2026-11-01", "2026-11-01")
    assert len(calls) == 1
    path.unlink()
    assert db.list_workouts("2026-11-01", "2026-11-01") == [] and len(calls) == 2
