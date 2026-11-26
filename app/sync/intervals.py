"""intervals.icu: Brücke zu Wahoo (und optional Garmin/Zwift).

intervals.icu überträgt geplante Workouts automatisch an Wahoo, wenn dort
unter Settings → Connections "Wahoo" verbunden und "Upload planned workouts"
aktiv ist. Der Bolt lädt sie dann beim nächsten Sync.

API-Schlüssel: intervals.icu → Settings → Developer Settings → API Key.
In .env eintragen: INTERVALS_API_KEY=... und INTERVALS_ATHLETE_ID=i12345
"""
from datetime import date, timedelta

import httpx

from .. import config
from ..workouts import fmt_duration, step_target

BASE = "https://intervals.icu/api/v1"
SPORT = {"ride": "Ride", "run": "Run", "swim": "Swim", "strength": "WeightTraining", "mobility": "Yoga",
         "other": "Workout"}
TARGET_SUFFIX = {"power": "", "pace": " Pace", "hr": " LTHR"}


def is_connected() -> bool:
    return bool(config.INTERVALS_API_KEY and config.INTERVALS_ATHLETE_ID)


def _http() -> httpx.Client:
    if not is_connected():
        raise RuntimeError("intervals.icu nicht konfiguriert (INTERVALS_API_KEY / INTERVALS_ATHLETE_ID in .env).")
    return httpx.Client(base_url=BASE, auth=("API_KEY", config.INTERVALS_API_KEY), timeout=20)


def _line(s: dict, workout: dict) -> str:
    suffix = TARGET_SUFFIX.get(step_target(workout, s), "")
    low, high = round(s.get("low", 0)), round(s.get("high", s.get("low", 0)))
    if not low and not high:  # Pause, Stabi, Dehnen: nur Dauer
        return f"- {fmt_duration(s['duration'])}"
    if s["kind"] in ("warmup", "cooldown") and low != high:
        a, b = (low, high) if s["kind"] == "warmup" else (high, low)
        return f"- {fmt_duration(s['duration'])} ramp {a}-{b}%{suffix}"
    target = f"{low}%" if low == high else f"{low}-{high}%"
    return f"- {fmt_duration(s['duration'])} {target}{suffix}"


def to_text(workout: dict) -> str:
    """Workout in der Textsyntax von intervals.icu (wird dort strukturiert geparst)."""
    blocks, current = [], []
    for s in workout.get("steps", []):
        if s.get("kind") == "repeat":
            if current:
                blocks.append("\n".join(current))
                current = []
            lines = [f"{int(s['count'])}x"] + [_line(c, workout) for c in s.get("steps", []) if c.get("kind") != "repeat"]
            blocks.append("\n".join(lines))
        else:
            current.append(_line(s, workout))
    if current:
        blocks.append("\n".join(current))
    text = "\n\n".join(blocks)
    if workout.get("description"):
        text = workout["description"] + "\n\n" + text
    return text


def push(workout: dict, settings: dict) -> dict:
    payload = {
        "category": "WORKOUT",
        "start_date_local": f"{workout['date']}T00:00:00",
        "type": SPORT.get(workout.get("sport", "other"), "Workout"),
        "name": workout.get("name", "Workout"),
        "description": to_text(workout),
    }
    existing = (workout.get("sync") or {}).get("intervals", {}).get("event_id")
    with _http() as h:
        path = f"/athlete/{config.INTERVALS_ATHLETE_ID}/events"
        r = h.put(f"{path}/{existing}", json=payload) if existing else h.post(path, json=payload)
        if existing and r.status_code == 404:
            r = h.post(path, json=payload)
        r.raise_for_status()
        return {"event_id": r.json()["id"]}


def remove(workout: dict) -> None:
    event_id = (workout.get("sync") or {}).get("intervals", {}).get("event_id")
    if event_id and is_connected():
        with _http() as h:
            h.delete(f"/athlete/{config.INTERVALS_ATHLETE_ID}/events/{event_id}")


def import_activities(settings: dict, days: int = 120) -> list[dict]:
    params = {"oldest": (date.today() - timedelta(days=days)).isoformat(), "newest": date.today().isoformat()}
    with _http() as h:
        r = h.get(f"/athlete/{config.INTERVALS_ATHLETE_ID}/activities", params=params)
        r.raise_for_status()
    sport_map = {"Ride": "ride", "VirtualRide": "ride", "GravelRide": "ride", "MountainBikeRide": "ride",
                 "Run": "run", "VirtualRun": "run", "TrailRun": "run", "Swim": "swim", "OpenWaterSwim": "swim",
                 "WeightTraining": "strength", "Yoga": "mobility", "Pilates": "mobility"}
    return [{
        "id": f"intervals:{a['id']}",
        "date": a["start_date_local"][:10],
        "sport": sport_map.get(a.get("type"), "other"),
        "name": a.get("name") or "Aktivität",
        "duration": int(a.get("moving_time") or 0),
        "tss": float(a.get("icu_training_load") or 0),
        "distance": float(a.get("distance") or 0),
        "metrics": {k: v for k, v in {
            "avg_hr": a.get("average_heartrate"), "np": a.get("icu_weighted_avg_watts"),
            "speed": a.get("average_speed"), "hr_zones": a.get("icu_hr_zone_times"),
            "avg_power": a.get("icu_average_watts"), "start_time": a.get("start_date_local"),
            "elevation_gain": a.get("total_elevation_gain"),
        }.items() if v} | ({"indoor": True} if a.get("type") in ("VirtualRide", "VirtualRun") or a.get("trainer") else {}),
    } for a in r.json() if a.get("start_date_local")]
