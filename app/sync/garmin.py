"""Garmin Connect: Workouts hochladen und im Garmin-Kalender einplanen.

Die Uhr holt sich geplante Workouts beim nächsten Sync
automatisch aus dem Garmin-Connect-Kalender.

Nutzt die inoffizielle Bibliothek `garminconnect`. Einmalig anmelden im Einrichtungsdialog (login/login_mfa)
oder im Terminal mit  .venv/bin/python -m app.garmin_login
Danach liegen Tokens in ~/.trainingsapp/garmin_tokens.
"""
from datetime import date, timedelta

import re

from .. import config
from ..templates import circuit_exercises, circuit_for
from ..workouts import flatten, repeat, step_target

SPORT_TYPES = {
    "run": {"sportTypeId": 1, "sportTypeKey": "running"},
    "ride": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "other": {"sportTypeId": 3, "sportTypeKey": "other"},
    "swim": {"sportTypeId": 4, "sportTypeKey": "swimming"},
    "strength": {"sportTypeId": 5, "sportTypeKey": "strength_training"},
    "mobility": {"sportTypeId": 3, "sportTypeKey": "other"},  # Dehnen/Yoga als "Sonstiges"
}
STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "steady": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest"},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat"},
}
# Kraft-Zirkel: Übungsname (deutsch/englisch) → Garmin-Übungskatalog (category, exerciseName), erste Zeile gewinnt.
# Geprüft gegen https://connect.garmin.com/web-data/exercises/Exercises.json – unbekannte Übungen nur als Notiz.
EXERCISES = [
    (r"seitstütz|side ?plank", "PLANK", "SIDE_PLANK"),
    (r"mountain ?climber|bergsteiger", "PLANK", "MOUNTAIN_CLIMBER"),
    (r"plank|unterarmstütz", "PLANK", "PLANK"),
    (r"(?=.*(bridge|beckenheben|hip raise))(?=.*(einbein|single))", "HIP_RAISE", "SINGLE_LEG_HIP_RAISE"),
    (r"bridge|beckenheben|hip raise", "HIP_RAISE", "HIP_RAISE"),
    (r"dead ?bug", "HIP_STABILITY", "DEAD_BUG"),
    (r"ausfallschritt|lunge", "LUNGE", "LUNGE"),
    (r"wadenheben|calf", "CALF_RAISE", "STANDING_CALF_RAISE"),
    (r"bulg|split ?squat", "LUNGE", "DUMBBELL_BULGARIAN_SPLIT_SQUAT"),
    (r"wandsitz|wall ?sit", "SQUAT", "BODY_WEIGHT_WALL_SQUAT"),
    (r"(?=.*(kniebeuge|squat))(?=.*(einbein|single))", "SQUAT", "PARTIAL_SINGLE_LEG_SQUAT"),
    (r"kniebeuge|squat", "SQUAT", "SQUAT"),
    (r"(?=.*(rudern|row))(?=.*band)", "BANDED_EXERCISES", "ROW"),
    (r"(?=.*(kreuzheben|deadlift))(?=.*(einbein|single))", "DEADLIFT", "SINGLE_LEG_ROMANIAN_DEADLIFT_WITH_DUMBBELL"),
    (r"liegestütz|push ?up", "PUSH_UP", "PUSH_UP"),
    (r"burpee", "TOTAL_BODY", "BURPEE"),
    (r"russian twist", "CORE", "RUSSIAN_TWIST"),
    (r"crunch", "CRUNCH", "CRUNCH"),
    (r"superman", "HYPEREXTENSION", "SUPERMAN_FROM_FLOOR"),
]
TARGET_TYPES = {
    "none": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target"},
    "power": {"workoutTargetTypeId": 2, "workoutTargetTypeKey": "power.zone"},
    "hr": {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"},
    "pace": {"workoutTargetTypeId": 6, "workoutTargetTypeKey": "pace.zone"},
}

_client = None


def client():
    """Angemeldeten Garmin-Client liefern (Tokens aus der einmaligen Anmeldung)."""
    global _client
    if _client is None:
        from garminconnect import Garmin

        if not config.GARMIN_TOKEN_DIR.exists():
            raise RuntimeError("Nicht bei Garmin angemeldet – in den Einstellungen „Einrichtung“ öffnen und Garmin verbinden.")
        g = Garmin()
        g.login(str(config.GARMIN_TOKEN_DIR))
        _client = g
    return _client


def is_connected() -> bool:
    return config.GARMIN_TOKEN_DIR.exists()


# Anmeldung aus dem Browser (Einrichtungsdialog). Das Passwort wird nicht gespeichert, nur die Sitzungs-Tokens.
_pending_mfa: dict = {}


def _store_login(g) -> str:
    global _client
    config.GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    g.client.dump(str(config.GARMIN_TOKEN_DIR))
    _client = g
    return g.get_full_name() or ""


def login(email: str, password: str) -> dict:
    """Mit E-Mail und Passwort anmelden. {"mfa": True}, wenn Garmin einen Code verlangt (dann login_mfa)."""
    from garminconnect import Garmin

    _pending_mfa.clear()
    g = Garmin(email.strip(), password, return_on_mfa=True)
    status, state = g.login()
    if status:  # "needs_mfa": Code per E-Mail/App, Anmeldung später fortsetzen
        _pending_mfa.update(garmin=g, state=state)
        return {"mfa": True}
    return {"mfa": False, "name": _store_login(g)}


def login_mfa(code: str) -> dict:
    if not _pending_mfa:
        raise RuntimeError("Keine Anmeldung wartet auf einen Code – bitte E-Mail und Passwort erneut senden.")
    g, state = _pending_mfa["garmin"], _pending_mfa["state"]
    g.resume_login(state, code.strip())
    _pending_mfa.clear()
    return {"mfa": False, "name": _store_login(g)}


def lthr_for(sport: str, settings: dict) -> float:
    return settings["lthr_ride"] if sport == "ride" else settings["lthr_run"]


def threshold_speed(sport: str, settings: dict) -> float:
    """Schwellengeschwindigkeit in m/s: CSS beim Schwimmen, Schwellentempo beim Laufen."""
    return 100 / settings["css"] if sport == "swim" else 1000 / settings["threshold_pace"]


def _target(workout: dict, s: dict, settings: dict) -> dict:
    target, sport = step_target(workout, s), workout.get("sport")
    low, high = float(s.get("low", 0)) / 100, float(s.get("high", s.get("low", 0))) / 100
    if sport in ("strength", "mobility") or not low:
        return {"targetType": TARGET_TYPES["none"]}
    if target == "power":
        values = (low * settings["ftp"], high * settings["ftp"])
    elif target == "hr":
        values = (low * lthr_for(sport, settings), high * lthr_for(sport, settings))
    else:  # pace → Geschwindigkeit in m/s
        values = (low * threshold_speed(sport, settings), high * threshold_speed(sport, settings))
    return {
        "targetType": TARGET_TYPES[target],
        "targetValueOne": round(values[0], 3),
        "targetValueTwo": round(values[1], 3),
    }


def exercise(name: str) -> dict:
    """Garmin-Felder einer Zirkel-Übung: Name als Notiz, dazu die Katalog-Übung, falls bekannt."""
    match = next(((cat, ex) for pattern, cat, ex in EXERCISES if re.search(pattern, name.lower())), None)
    return {"description": name, **({"category": match[0], "exerciseName": match[1]} if match else {})}


def circuit_steps(workout: dict) -> list[dict] | None:
    """Kraft-Zirkel als Schritte: Aufwärmen/Abkühlen aus dem Workout, dazwischen je Runde jede Übung + Pause."""
    circuit = circuit_for(workout) if workout.get("sport") == "strength" else None
    if not circuit:
        return None
    exercises = circuit_exercises(circuit) or [{"name": ""}]
    round_steps = []
    for i, ex in enumerate(exercises):
        # Dauer bei Wiederholungen nur als Schätzung (für die Gesamtdauer)
        round_steps.append({"kind": "interval", "duration": ex.get("seconds", circuit["work"]), "low": 0, "high": 0,
                            "exercise": ex["name"], **({"reps": ex["reps"]} if "reps" in ex else {})})
        pause = circuit["round_rest"] if i == len(exercises) - 1 and circuit["round_rest"] else circuit["rest"]
        if pause:
            round_steps.append({"kind": "rest", "duration": pause, "low": 0, "high": 0})
    steps = workout.get("steps", [])
    return ([s for s in steps if s.get("kind") == "warmup"] + [repeat(circuit["rounds"], *round_steps)]
            + [s for s in steps if s.get("kind") == "cooldown"])


def _end(s: dict) -> dict:
    """Schrittende: Zeit, Wiederholungen (Kraft) oder – Wiederholungen ohne Zahl – Runden-Taste."""
    if "reps" not in s:
        return {"endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time"}, "endConditionValue": int(s["duration"])}
    if not s["reps"]:
        return {"endCondition": {"conditionTypeId": 1, "conditionTypeKey": "lap.button"}}
    return {"endCondition": {"conditionTypeId": 10, "conditionTypeKey": "reps"}, "endConditionValue": int(s["reps"])}


def _steps(workout: dict, steps: list[dict], settings: dict, counter: list[int]) -> list[dict]:
    out = []
    for s in steps:
        counter[0] += 1
        if s.get("kind") == "repeat":
            out.append({
                "type": "RepeatGroupDTO",
                "stepOrder": counter[0],
                "stepType": STEP_TYPES["repeat"],
                "numberOfIterations": int(s["count"]),
                "endCondition": {"conditionTypeId": 7, "conditionTypeKey": "iterations"},
                "endConditionValue": int(s["count"]),
                "smartRepeat": False,
                # Kraft-Zirkel: keine Rundenpause nach der letzten Runde; Rad/Lauf/Schwimmen unverändert
                "skipLastRestStep": workout.get("sport") == "strength",
                "workoutSteps": _steps(workout, s.get("steps", []), settings, counter),
            })
        else:
            out.append({
                "type": "ExecutableStepDTO",
                "stepOrder": counter[0],
                "stepType": STEP_TYPES.get(s["kind"], STEP_TYPES["interval"]),
                **_end(s),
                **_target(workout, s, settings),
                **(exercise(s["exercise"]) if s.get("exercise") else {}),
            })
    return out


def to_garmin_json(workout: dict, settings: dict) -> dict:
    sport = SPORT_TYPES.get(workout.get("sport", "other"), SPORT_TYPES["other"])
    steps = circuit_steps(workout) or workout.get("steps", [])
    return {
        "workoutName": workout.get("name", "Workout")[:80],
        "description": workout.get("description", ""),
        "sportType": sport,
        "estimatedDurationInSecs": sum(int(s["duration"]) for s in flatten(steps)),
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": sport,
            "workoutSteps": _steps(workout, steps, settings, [0]),
        }],
    }


def push(workout: dict, settings: dict) -> dict:
    g = client()
    remove(workout)
    created = g.upload_workout(to_garmin_json(workout, settings))
    workout_id = created["workoutId"]
    scheduled = g.schedule_workout(workout_id, workout["date"])
    return {"workout_id": workout_id, "schedule_id": (scheduled or {}).get("workoutScheduleId")}


def remove(workout: dict) -> None:
    info = (workout.get("sync") or {}).get("garmin")
    if info and info.get("workout_id"):
        try:
            client().delete_workout(info["workout_id"])  # entfernt auch den Kalendereintrag
        except Exception:
            pass  # wurde evtl. schon in Garmin Connect gelöscht


# --- Import erledigter Aktivitäten ----------------------------------------

def _sport(type_key: str) -> str:
    if "swim" in type_key:
        return "swim"
    if any(k in type_key for k in ("cycling", "biking", "ride")):
        return "ride"
    if "running" in type_key or "run" in type_key:
        return "run"
    if "strength" in type_key:
        return "strength"
    if any(k in type_key for k in ("yoga", "pilates", "stretch", "mobility", "breathwork")):
        return "mobility"
    return "other"


def activity_tss(a: dict, settings: dict, sport: str = "") -> float:
    """TSS: Garmin-Wert falls vorhanden, sonst aus Normalized Power bzw. Puls (hrTSS) geschätzt."""
    if a.get("trainingStressScore"):
        return float(a["trainingStressScore"])
    seconds = float(a.get("movingDuration") or a.get("duration") or 0)
    hours = seconds / 3600
    if a.get("normPower") and settings.get("ftp"):
        return hours * (a["normPower"] / settings["ftp"]) ** 2 * 100
    if a.get("averageHR") and sport in ("ride", "run", "swim"):
        return hours * (a["averageHR"] / lthr_for(sport, settings)) ** 2 * 100
    return hours * 50


INDOOR_TYPES = {"indoor_cycling", "virtual_ride", "treadmill_running", "indoor_running", "virtual_run"}
MMP_DURATIONS = (1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200)  # Sekunden


def activity_metrics(a: dict, sport: str) -> dict:
    """Kennzahlen aus der Garmin-Zusammenfassung – reicht für EF, Zonenzeiten und Leistungskurve.

    speed/gap in m/s (gap = steigungsbereinigt), hr_zones = Sekunden in Pulszone 1–5,
    mmp = beste Durchschnittsleistung je Dauer (nur Rad).
    """
    type_key = (a.get("activityType") or {}).get("typeKey", "")
    m = {
        "avg_hr": a.get("averageHR"), "max_hr": a.get("maxHR"), "np": a.get("normPower"),
        "avg_power": a.get("avgPower"), "speed": a.get("averageSpeed"), "gap": a.get("avgGradeAdjustedSpeed"),
        "if": a.get("intensityFactor"),
        # für die EF-Regeln (analysis._not_comparable): Koppellauf, Rolle/Laufband, Wettkampf, Intervalle, Hügel
        "start_time": a.get("startTimeLocal"), "indoor": type_key in INDOOR_TYPES,
        "event_type": (a.get("eventType") or {}).get("typeKey"),
        "anaerobic_te": a.get("anaerobicTrainingEffect"), "elevation_gain": a.get("elevationGain"),
        # Uhrsensor: das Maximum ist vom Handgelenk aufgeheizt, das Minimum liegt näher an der Lufttemperatur
        "temp": None if type_key in INDOOR_TYPES else a.get("minTemperature"),
    }
    zones = [a.get(f"hrTimeInZone_{i}") for i in range(1, 6)]
    if any(zones):
        m["hr_zones"] = [round(z or 0) for z in zones]
    if sport == "ride":
        mmp = {str(d): a[f"maxAvgPower_{d}"] for d in MMP_DURATIONS if a.get(f"maxAvgPower_{d}")}
        if mmp:
            m["mmp"] = mmp
    return {k: v for k, v in m.items() if v is not None}


def import_activities(settings: dict, days: int = 120) -> list[dict]:
    start = (date.today() - timedelta(days=days)).isoformat()
    raw = client().get_activities_by_date(start, date.today().isoformat())
    out = []
    for a in raw:
        sport = _sport(a.get("activityType", {}).get("typeKey", ""))
        out.append({
            "id": f"garmin:{a['activityId']}",
            "date": a["startTimeLocal"][:10],
            "sport": sport,
            "name": a.get("activityName") or "Aktivität",
            "duration": int(a.get("movingDuration") or a.get("duration") or 0),
            "tss": round(activity_tss(a, settings, sport), 1),
            "distance": float(a.get("distance") or 0),
            "metrics": activity_metrics(a, sport),
        })
    return out


def parse_profile(ftp_raw, lactate_raw: dict, zones_raw: list) -> dict:
    """Garmin-Antworten → Einstellungen (ftp, lthr_run, lthr_ride, threshold_pace, max_hr).

    Fehlende Werte fehlen im Ergebnis. CSS kommt separat (css_seconds), siehe main.refresh_settings_from_garmin.
    """
    out = {}
    ftp = (ftp_raw[0] if ftp_raw else {}) if isinstance(ftp_raw, list) else (ftp_raw or {})
    if ftp.get("functionalThresholdPower"):
        out["ftp"] = round(ftp["functionalThresholdPower"])
    lt = (lactate_raw or {}).get("speed_and_heart_rate") or {}
    zones = {z.get("sport"): z for z in zones_raw or []}
    if lt.get("heartRate"):
        out["lthr_run"] = int(lt["heartRate"])
    lthr_ride = lt.get("heartRateCycling") or (zones.get("CYCLING") or {}).get("lactateThresholdHeartRateUsed")
    if lthr_ride:
        out["lthr_ride"] = int(lthr_ride)
    if lt.get("speed"):
        out["threshold_pace"] = round(1000 / (lt["speed"] * 10))  # Garmin liefert die Schwelle in 10 m/s
    weight = ((lactate_raw or {}).get("power") or {}).get("weight")
    if weight:
        out["weight"] = round(float(weight), 1)
    max_hr = (zones.get("DEFAULT") or zones.get("RUNNING") or {}).get("maxHeartRateUsed")
    if max_hr:
        out["max_hr"] = int(max_hr)
    return out


def import_profile() -> dict:
    """Aktuelle Rad-FTP, Laktatschwelle (Puls Lauf/Rad + Tempo) und Max-Puls aus Garmin Connect."""
    g = client()
    raw = {}
    for key, fetch in (("ftp_raw", g.get_cycling_ftp),
                       ("lactate_raw", lambda: g.get_lactate_threshold(latest=True)),
                       ("zones_raw", g.get_heart_rate_zones),
                       ("css_raw", g.get_critical_swim_speed)):
        try:
            raw[key] = fetch()
        except Exception:
            raw[key] = None  # einzelner Wert fehlt → die anderen trotzdem übernehmen
    css = css_seconds(raw.pop("css_raw"))
    return {**parse_profile(**raw), **({"css_garmin": css} if css else {})}


def import_wellness(day: str) -> dict:
    """Trainingsbereitschaft und HRV-Status des Tages (falls die Uhr sie liefert)."""
    g = client()
    out = {}
    try:
        readiness = g.get_training_readiness(day)
        if isinstance(readiness, list) and readiness:
            out["readiness"] = readiness[0].get("score")
    except Exception:
        pass
    try:
        hrv = g.get_hrv_data(day) or {}
        out["hrv_status"] = (hrv.get("hrvSummary") or {}).get("status")
    except Exception:
        pass
    return out


# --- Kennzahlen, die Garmin selbst berechnet -------------------------------

TRAINING_STATUS_DE = {
    "PRODUCTIVE": "Produktiv", "MAINTAINING": "Erhaltend", "RECOVERY": "Erholung", "UNPRODUCTIVE": "Unproduktiv",
    "DETRAINING": "Leistungsabbau", "OVERREACHING": "Überlastung", "PEAKING": "Höchstform",
    "STRAINED": "Angespannt", "NO": "Kein Status",
}


def css_seconds(raw: dict) -> dict | None:
    """Garmin-CSS (mm/s) → {"css": Sekunden pro 100 m, "at": Messzeitpunkt}."""
    speed = (raw or {}).get("criticalSwimSpeed")
    if not speed:
        return None
    return {"css": round(100 / (speed / 1000)), "at": raw.get("measurementTimestampLocal", "")}


def _vo2(entry: dict, key: str):
    return ((entry or {}).get(key) or {}).get("vo2MaxPreciseValue")


def import_metrics(today: date) -> dict:
    """Kennzahlen für die Analyse-Seite. Fehlt ein Wert, bleibt er None (Garmin liefert nicht alles für jeden)."""
    g = client()
    t, ago90, ago365 = today.isoformat(), (today - timedelta(days=90)).isoformat(), (today - timedelta(days=365)).isoformat()

    def safe(fn):
        try:
            return fn()
        except Exception:
            return None

    out = {}
    status = safe(lambda: g.get_training_status(t)) or {}
    latest = next(iter(((status.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {}).values()), {})
    acute = latest.get("acuteTrainingLoadDTO") or {}
    phrase = (latest.get("trainingStatusFeedbackPhrase") or "").split("_")[0]
    out["training_status"] = {
        "label": TRAINING_STATUS_DE.get(phrase, phrase.title() or None),
        "acute_load": acute.get("dailyTrainingLoadAcute"), "chronic_load": acute.get("dailyTrainingLoadChronic"),
        "ratio": acute.get("dailyAcuteChronicWorkloadRatio"), "ratio_status": acute.get("acwrStatus"),
    } if latest else None
    vo2 = status.get("mostRecentVO2Max") or {}
    out["vo2max"] = {"run": _vo2(vo2, "generic"), "ride": _vo2(vo2, "cycling")}
    out["vo2max_series"] = [
        {"date": (e.get("generic") or e.get("cycling") or {}).get("calendarDate"),
         "run": _vo2(e, "generic"), "ride": _vo2(e, "cycling")}
        for e in safe(lambda: g.get_max_metrics_range(ago90, t)) or [] if isinstance(e, dict)
    ]
    heat = safe(lambda: g.get_heat_altitude_acclimation(t)) or {}
    out["heat_acclimation"] = heat.get("heatAcclimationPercentage")
    endurance = safe(lambda: g.get_endurance_score(ago90, t)) or {}
    series = [{"date": d, "value": v.get("groupAverage")} for d, v in sorted((endurance.get("groupMap") or {}).items())]
    out["endurance"] = {"current": series[-1]["value"], "series": series} if series else None
    pred = safe(g.get_race_predictions) or {}
    out["race_predictions"] = {k: pred.get(f"time{k}") for k in ("5K", "10K", "HalfMarathon", "Marathon")} if pred else None
    ftp = safe(lambda: g.get_functional_threshold_power_range(ago365, t, sport="CYCLING")) or []
    out["ftp_series"] = [{"date": e["from"], "value": e["value"]} for e in ftp if isinstance(e, dict) and e.get("value")]
    out["css"] = css_seconds(safe(lambda: g.get_critical_swim_speed(t)))
    return out
