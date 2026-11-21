"""SQLite-Speicher: geplante Workouts, importierte Aktivitäten, Wellness-Daten, Einstellungen."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

DEFAULT_SETTINGS = {
    "ftp": 250,                  # Watt (Rad)
    "lthr_run": 170,             # Laktatschwellen-Puls Laufen (bpm)
    "lthr_ride": 165,            # Laktatschwellen-Puls Rad (bpm)
    "max_hr": 190,
    "threshold_pace": 300,       # Laufen: Sekunden pro km an der Schwelle (5:00/km)
    "css": 105,                  # Schwimmen: Critical Swim Speed in Sekunden pro 100 m (1:45)
    "zwift_dir": "",             # leer = automatisch ~/Documents/Zwift/Workouts/<id>
    "race_type": "ironman",      # ironman | half | other → Blocklängen (periodization.RACE_PLANS)
    "goal_name": "",             # wird im Einrichtungsdialog beim ersten Start abgefragt
    "goal_date": "",             # YYYY-MM-DD
    "week_hours": 10,            # Stunden in einer normalen Belastungswoche
    "recovery_every": 4,         # jede n-te Woche Entlastung (0 = aus)
    "cycle_start": "",           # Montag der 1. Belastungswoche; leer = Rhythmus rückwärts vom Wettkampf
    "taper_weeks": 0,            # Taper inkl. Rennwoche; 0 = Standard der Wettkampfart (Ironman 3)
    "auto_sync": [],             # z.B. ["garmin", "zwift", "intervals", "google"]
    "google_calendar": "Sport",  # Name des Google-Kalenders für geplante Workouts
    "garmin_profile": True,      # FTP, LTHR, Schwellentempo, Max-Puls beim Öffnen von Garmin holen
    "garmin_profile_at": "",     # Zeitpunkt der letzten Übernahme
    "css_garmin_seen": "",       # Zeitpunkt der zuletzt gesehenen Garmin-CSS-Messung (nur neuere werden übernommen)
    "target_ctl": 0,             # Ziel-Fitness (CTL) zu Beginn des Taperings, 0 = aus
    "weight": 0,                 # kg, für Verpflegungsplan (von Garmin, falls vorhanden)
    "sweat_rate": 0,             # l/h Schweißverlust (vorher/nachher wiegen), 0 = unbekannt → Trinken nach Durst
    "plant_based": False,        # vegetarisch/vegan → Ernährungshinweise mit pflanzlichem Protein
    "setup_done": False,         # Einrichtungsdialog abgeschlossen (neue Datenbanken starten mit False)
    "race_plan": {},             # Eingaben der Renntag-Planung (Analyse → Renntag)
    # Wochenmuster: Einheiten je Wochentag (leere Liste = Ruhetag).
    # type: recovery | easy | hard | long; sport: swim | ride | run | strength | mobility
    "week_pattern": {
        "mon": [{"type": "easy", "sport": "mobility"}],
        "tue": [{"type": "hard", "sport": "ride"}, {"type": "easy", "sport": "strength"}],
        "wed": [{"type": "hard", "sport": "swim"}, {"type": "easy", "sport": "run"}],
        "thu": [{"type": "hard", "sport": "run"}, {"type": "easy", "sport": "ride"}],
        "fri": [{"type": "easy", "sport": "swim"}, {"type": "easy", "sport": "strength"}],
        "sat": [{"type": "easy", "sport": "swim"}, {"type": "long", "sport": "ride"}],
        "sun": [{"type": "long", "sport": "run"}, {"type": "easy", "sport": "mobility"}],
    },
}


# Standard-Wochenmuster der ersten Version (eine Einheit pro Tag, ohne Schwimmen)
_OLD_DEFAULT_PATTERN = {
    "mon": {"type": "rest", "sport": "ride"}, "tue": {"type": "hard", "sport": "ride"},
    "wed": {"type": "easy", "sport": "run"}, "thu": {"type": "hard", "sport": "run"},
    "fri": {"type": "recovery", "sport": "ride"}, "sat": {"type": "long", "sport": "ride"},
    "sun": {"type": "long", "sport": "run"},
}


def _migrate_settings(stored: dict) -> dict:
    """Ältere Einstellungen ins aktuelle Format bringen."""
    if "lthr" in stored:  # früher ein Wert für alle Sportarten
        stored.setdefault("lthr_run", stored["lthr"])
        stored.setdefault("lthr_ride", stored["lthr"])
    pattern = stored.get("week_pattern")
    if pattern == _OLD_DEFAULT_PATTERN:  # nie angepasst → neues Triathlon-Muster verwenden
        del stored["week_pattern"]
    elif pattern and any(isinstance(v, dict) for v in pattern.values()):  # früher eine Einheit pro Tag
        stored["week_pattern"] = {d: [] if v.get("type") == "rest" else [v] for d, v in pattern.items()}
    return stored


SCHEMA = """
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,          -- "<quelle>:<id>"
    date TEXT NOT NULL,
    sport TEXT,
    name TEXT,
    duration INTEGER,             -- Sekunden
    tss REAL,
    distance REAL,                -- Meter
    metrics TEXT                  -- JSON: avg_hr, np, speed, gap, if, hr_zones [s], mmp {Sekunden: Watt}
);
CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date);
CREATE TABLE IF NOT EXISTS wellness (
    date TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    activity_id TEXT PRIMARY KEY, -- Feedback zu importierten Aktivitäten (Workouts speichern es selbst)
    data TEXT NOT NULL            -- JSON: rpe 0–10, feel 1–5, note
);
CREATE TABLE IF NOT EXISTS races (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL            -- JSON: name, date, priority (B|C), race_type
);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,         -- z. B. Garmin-Kennzahlen, damit nicht bei jedem Öffnen abgefragt wird
    fetched_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_db_path: Path = config.DB_PATH


def set_db_path(path: Path) -> None:
    """Für Tests: andere Datenbankdatei verwenden."""
    global _db_path
    _db_path = path


@contextmanager
def connect():
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    new = not _db_path.exists()
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if new:  # neue Installation: Einrichtungsdialog zeigen (alte Datenbanken erkennt man am fehlenden Eintrag)
        conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('setup_done', 'false')")
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(activities)")}
    for column, kind in (("distance", "REAL"), ("metrics", "TEXT")):  # Datenbanken aus älteren Versionen
        if column not in columns:
            conn.execute(f"ALTER TABLE activities ADD COLUMN {column} {kind}")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Einstellungen ---------------------------------------------------------

def get_settings() -> dict:
    with connect() as c:
        stored = {r["key"]: json.loads(r["value"]) for r in c.execute("SELECT key, value FROM settings")}
        if "setup_done" not in stored:  # Datenbank von vor dem Einrichtungsdialog: gilt als eingerichtet
            c.execute("REPLACE INTO settings(key, value) VALUES ('setup_done', 'true')")
            stored["setup_done"] = True
    return {**DEFAULT_SETTINGS, **_migrate_settings(stored)}


def save_settings(values: dict) -> dict:
    with connect() as c:
        for key, value in values.items():
            if key in DEFAULT_SETTINGS:
                c.execute("REPLACE INTO settings(key, value) VALUES (?, ?)", (key, json.dumps(value)))
    return get_settings()


# --- Workouts --------------------------------------------------------------

def _row_to_workout(row) -> dict:
    return {**json.loads(row["data"]), "id": row["id"], "date": row["date"]}


def list_workouts(start: str, end: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM workouts WHERE date >= ? AND date <= ? ORDER BY date", (start, end)
        ).fetchall()
    return [_row_to_workout(r) for r in rows]


def get_workout(workout_id: int) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT * FROM workouts WHERE id = ?", (workout_id,)).fetchone()
    return _row_to_workout(row) if row else None


def save_workout(workout: dict) -> dict:
    data = {k: v for k, v in workout.items() if k not in ("id", "date")}
    with connect() as c:
        if workout.get("id"):
            c.execute(
                "UPDATE workouts SET date = ?, data = ? WHERE id = ?",
                (workout["date"], json.dumps(data), workout["id"]),
            )
            workout_id = workout["id"]
        else:
            cur = c.execute("INSERT INTO workouts(date, data) VALUES (?, ?)", (workout["date"], json.dumps(data)))
            workout_id = cur.lastrowid
    return get_workout(workout_id)


def delete_workout(workout_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM workouts WHERE id = ?", (workout_id,))


# --- Aktivitäten & Wellness ------------------------------------------------

def upsert_activities(items: list[dict]) -> int:
    with connect() as c:
        for a in items:
            c.execute(
                "REPLACE INTO activities(id, date, sport, name, duration, tss, distance, metrics) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (a["id"], a["date"], a["sport"], a["name"], a["duration"], a["tss"], a.get("distance"),
                 json.dumps(a.get("metrics") or {})),
            )
    return len(items)


def list_activities(start: str, end: str) -> list[dict]:
    """Aktivitäten mit Kennzahlen (`metrics`) und Feedback (`feedback`, falls vorhanden)."""
    with connect() as c:
        rows = c.execute(
            "SELECT a.*, f.data AS feedback FROM activities a LEFT JOIN feedback f ON f.activity_id = a.id "
            "WHERE a.date >= ? AND a.date <= ? ORDER BY a.date", (start, end)
        ).fetchall()
    return [{**dict(r), "metrics": json.loads(r["metrics"] or "{}"), "feedback": json.loads(r["feedback"] or "{}")}
            for r in rows]


def get_feedback(activity_id: str) -> dict:
    with connect() as c:
        row = c.execute("SELECT data FROM feedback WHERE activity_id = ?", (activity_id,)).fetchone()
    return json.loads(row["data"]) if row else {}


def save_feedback(activity_id: str, data: dict) -> None:
    with connect() as c:
        if data:
            c.execute("REPLACE INTO feedback(activity_id, data) VALUES (?, ?)", (activity_id, json.dumps(data)))
        else:
            c.execute("DELETE FROM feedback WHERE activity_id = ?", (activity_id,))


def upsert_wellness(date: str, data: dict) -> None:
    with connect() as c:
        c.execute("REPLACE INTO wellness(date, data) VALUES (?, ?)", (date, json.dumps(data)))


def get_wellness(date: str) -> dict:
    with connect() as c:
        row = c.execute("SELECT data FROM wellness WHERE date = ?", (date,)).fetchone()
    return json.loads(row["data"]) if row else {}


# --- Ziele -----------------------------------------------------------------

def list_goals() -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM goals ORDER BY id").fetchall()
    return [{**json.loads(r["data"]), "id": r["id"]} for r in rows]


def save_goal(goal: dict) -> dict:
    data = json.dumps({k: v for k, v in goal.items() if k != "id"})
    with connect() as c:
        if goal.get("id"):
            c.execute("UPDATE goals SET data = ? WHERE id = ?", (data, goal["id"]))
            goal_id = goal["id"]
        else:
            goal_id = c.execute("INSERT INTO goals(data) VALUES (?)", (data,)).lastrowid
    return next(g for g in list_goals() if g["id"] == goal_id)


def delete_goal(goal_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM goals WHERE id = ?", (goal_id,))


# --- Wettkämpfe (B/C; das A-Rennen steht in den Einstellungen) --------------

def list_races() -> list[dict]:
    with connect() as c:
        rows = c.execute("SELECT * FROM races").fetchall()
    return sorted(({**json.loads(r["data"]), "id": r["id"]} for r in rows), key=lambda r: r["date"])


def save_race(race: dict) -> dict:
    data = json.dumps({k: v for k, v in race.items() if k != "id"})
    with connect() as c:
        if race.get("id"):
            c.execute("UPDATE races SET data = ? WHERE id = ?", (data, race["id"]))
            race_id = race["id"]
        else:
            race_id = c.execute("INSERT INTO races(data) VALUES (?)", (data,)).lastrowid
    return next(r for r in list_races() if r["id"] == race_id)


def delete_race(race_id: int) -> None:
    with connect() as c:
        c.execute("DELETE FROM races WHERE id = ?", (race_id,))


# --- Zwischenspeicher für externe Abfragen ----------------------------------

def get_cache(key: str) -> tuple[str, object] | None:
    with connect() as c:
        row = c.execute("SELECT fetched_at, data FROM cache WHERE key = ?", (key,)).fetchone()
    return (row["fetched_at"], json.loads(row["data"])) if row else None


def set_cache(key: str, fetched_at: str, data) -> None:
    with connect() as c:
        c.execute("REPLACE INTO cache(key, fetched_at, data) VALUES (?, ?, ?)", (key, fetched_at, json.dumps(data)))
