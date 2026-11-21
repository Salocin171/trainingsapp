"""Verpflegung vor, während und nach einer Einheit – angepasst an Gewicht, Art der Einheit und Trainingsphase.

Grundlage ist die geprüfte Kohlenhydrat-Logik aus dem Skill "tri-ernaehrung":

    Einheit                                   während (g/h)
    Lockere Radeinheit                        40–60 (unter 60 min: 0)
    … vor harter Folgeeinheit                 60–90
    Intervalle (VO2max/Schwelle) bis 75 min   0–30
    Sweet Spot / Schwelle 75–120 min          45–60
    Lange Radeinheit / Renntempo              90 (Grundlage) → 90–100 → 100–120 (letzte 12 Wochen)
    Koppellauf                                60–90
    Langer Lauf                               45–60 → 75–90 (letzte 12 Wochen)
    Lockerer Lauf                             0
    Schwimmen ab 75 min                       0–30

    Vorher:  1–1,5 g/kg (locker), 1–2 g/kg (Intervalle), 2–3 g/kg (lange Radeinheit), 2–3 h vorher.
             Frühe Einheiten (Start vor 9 Uhr): 0,5–1 g/kg 60–90 min vorher, Vorabend KH-betont.
    Danach:  nächste Qualitätseinheit in < 8 h → 1,0–1,2 g/kg/h über 4 h (+ 0,2–0,4 g/kg/h Protein),
             sonst Mahlzeit mit 1–1,5 g/kg KH + 30–40 g Protein (pflanzlich, wenn plant_based).
    Tag:     3–5 g/kg (Ruhetag) · 5–7 (moderat) · 6–10 (hoch) · 8–12 (sehr hoch).
    Trinken: vorher 5–7 ml/kg (ACSM 2007); während nach Durst bzw. aus der Schweißrate so, dass der
             Verlust zwischen 1 und 2 % des Körpergewichts bleibt (NATA 2017); danach 125–150 % des Defizits.

Steht in der Beschreibung schon ein Block wie

    KH (75 kg):
    - Vorher: 170–255 g KH (2–3 g/kg) 2–3 h vorher.
    - Während: 90 g/h …
    - Danach: Mahlzeit mit 85–130 g KH + 30–40 g Protein; Tagesziel 6–10 g/kg …

gelten dessen Zahlen (er wurde für genau diese Einheit geplant); berechnet wird nur, was dort fehlt.
Startzeiten kommen aus dem Namen ("08:00 · Rad …").
"""
import re
from datetime import date, timedelta

from .workouts import flatten, total_duration

DEFAULT_WEIGHT = 75.0
ENDURANCE = ("ride", "run", "swim")
# Ab dieser Intensität (% der Schwelle) zählt ein Abschnitt als hart bzw. Sweet Spot/Tempo
HARD = {"ride": 95, "run": 95}
TEMPO = {"ride": 84, "run": 88}

KIND_LABEL = {
    "race_pace": "Renntempo", "long": "Lange Einheit", "quality": "Intensive Einheit", "easy": "Lockere Einheit",
    "brick": "Koppellauf", "strength": "Kraft / Stabi", "mobility": "Dehnen / Yoga", "other": "Sonstiges",
}
PHASES = ("before", "during", "after")
PLAN_LINE = re.compile(r"^\s*[-•·*]?\s*(Vorher|Während|Waehrend|Danach)\s*:\s*(.+?)\s*$", re.I | re.M)
NUM = r"(\d+(?:[,.]\d+)?)"
RANGE = NUM + r"(?:\s*[–-]\s*" + NUM + r")?"


def _f(text: str) -> float:
    return float(text.replace(",", "."))


def _q(low: float, high: float | None = None, unit: str = "g", per_kg: tuple | None = None) -> dict:
    """Menge als Bereich, gerundet auf 5 (g, ml) bzw. 1 (kleine Werte)."""
    high = low if high is None else high
    step = 5 if max(low, high) >= 30 else 1
    out = {"low": int(round(low / step) * step), "high": int(round(high / step) * step), "unit": unit}
    if per_kg:
        out["per_kg"] = per_kg
    return out


def start_time(workout: dict) -> str | None:
    """Startzeit aus dem Namen, z. B. "08:00 · Rad 2:30 h" → "08:00"."""
    m = re.match(r"\s*(\d{1,2})[:.](\d{2})\b", workout.get("name") or "")
    if m and int(m[1]) < 24 and int(m[2]) < 60:
        return f"{int(m[1]):02d}:{m[2]}"
    return None


def _minutes_of_day(hhmm: str | None) -> int | None:
    return int(hhmm[:2]) * 60 + int(hhmm[3:]) if hhmm else None


def _clock(minutes: float) -> str:
    minutes = int(round(minutes)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# --- Art der Einheit ---------------------------------------------------------

def classify(workout: dict) -> str:
    sport = workout.get("sport")
    if sport == "mobility" or (sport == "strength" and re.search(r"yoga|dehn|mobil", (workout.get("name") or "").lower())):
        return "mobility"
    if sport == "strength":
        return sport
    if sport not in ENDURANCE:
        return "other"
    name = (workout.get("name") or "").lower()
    minutes = total_duration(workout.get("steps", [])) / 60
    if sport == "run" and re.search(r"koppel|brick", name):
        return "brick"
    if workout.get("template") == "race_pace" or re.search(r"renntempo|wettkampftempo|race.?pace|im-pace", name):
        return "race_pace"
    if sport == "swim":
        return "long" if minutes >= 75 else "easy"
    hard = tempo = 0
    for s in flatten(workout.get("steps", [])):
        pct = (float(s.get("low", 0)) + float(s.get("high", s.get("low", 0)))) / 2
        if pct >= HARD[sport]:
            hard += s.get("duration", 0)
        elif pct >= TEMPO[sport]:
            tempo += s.get("duration", 0)
    if hard >= 6 * 60 or tempo >= 20 * 60:
        return "quality"
    if (sport == "ride" and minutes >= 150) or (sport == "run" and minutes >= 80):
        return "long"
    return "easy"


def is_key_session(workout: dict) -> bool:
    """Qualitätseinheit, vor der die Speicher voll sein sollen (Rad/Lauf: intensiv, lang oder Renntempo)."""
    return workout.get("sport") in ("ride", "run") and classify(workout) in ("quality", "long", "race_pace")


def weeks_to_race(day: date, settings: dict) -> float | None:
    if not settings.get("goal_date"):
        return None
    days = (date.fromisoformat(settings["goal_date"]) - day).days
    return days / 7 if days >= 0 else None


def _gut_training_rate(weeks: float | None) -> tuple[int, int, str]:
    """Darmtraining für lange Radeinheiten: Zielmenge steigt Richtung Rennen."""
    if weeks is not None and weeks <= 12:
        return 100, 120, "Darmtraining Rennphase: 100 → 120 g/h üben, Rennprodukte nutzen."
    if weeks is not None and weeks <= 16:
        return 90, 100, "Darmtraining: 90–100 g/h."
    return 90, 90, "Darmtraining: 90 g/h, Verträglichkeit notieren."


def during_rate(workout: dict, kind: str, weeks: float | None, key_session_follows: bool) -> tuple[int, int, str]:
    """(g/h von, bis, Begründung)."""
    sport, minutes = workout.get("sport"), total_duration(workout.get("steps", [])) / 60
    if sport == "ride":
        if kind in ("long", "race_pace"):
            return _gut_training_rate(weeks)
        if kind == "quality":
            if minutes <= 75:
                return 0, 30, "Kurz und intensiv: Speicher reichen, Mundspülung oder etwas Iso genügt."
            if minutes <= 120:
                return 45, 60, "Sweet Spot / Schwelle bis 2 h."
            return 60, 90, "Lang mit intensiven Blöcken."
        if minutes < 60:
            return 0, 0, "Unter 60 min locker: keine Verpflegung nötig."
        if key_session_follows:
            return 60, 90, "Locker, aber vor einer harten Folgeeinheit – Speicher schonen."
        return 40, 60, "Lockere Radeinheit."
    if sport == "run":
        if kind == "brick":
            return 60, 90, "Koppellauf: an die Rad-Verpflegung anschließen."
        long_rate = (75, 90, "Langer Lauf, Rennphase: Lauf-Verpflegung wie im Rennen üben.") \
            if weeks is not None and weeks <= 12 else (45, 60, "Langer Lauf.")
        if kind == "long" or (kind in ("quality", "race_pace") and minutes > 75):
            return long_rate
        if kind in ("quality", "race_pace"):
            return 0, 30, "Kurz und intensiv: Speicher reichen."
        return 0, 0, "Lockerer Lauf: keine Verpflegung nötig."
    if sport == "swim":
        if minutes >= 75:
            return 0, 30, "Lange Schwimmeinheit: z. B. Iso am Beckenrand."
        return 0, 0, "Kurze Schwimmeinheit: keine Verpflegung nötig."
    return 0, 0, ""


# --- Plan-Text aus der Beschreibung ------------------------------------------

def parse_plan(description: str) -> dict:
    """Vorher/Während/Danach-Zeilen und ihre Zahlen aus der Beschreibung lesen."""
    out: dict = {}
    for m in PLAN_LINE.finditer(description or ""):
        key = {"vorher": "before", "während": "during", "waehrend": "during", "danach": "after"}[m[1].lower()]
        out.setdefault(key, {"text": m[2]})
    if "during" in out:
        rates = [(_f(a), _f(b or a)) for a, b in re.findall(RANGE + r"\s*g\s*(?:KH\s*)?/\s*h", out["during"]["text"])]
        if rates:
            out["during"]["carbs"] = (min(r[0] for r in rates), max(r[1] for r in rates))
    grams = RANGE + r"\s*g(?!\s*/)(?!\w)"
    if "before" in out:
        m = re.search(grams, out["before"]["text"])
        if m:
            out["before"]["carbs"] = (_f(m[1]), _f(m[2] or m[1]))
    if "after" in out:
        text = out["after"]["text"]
        day = re.search(r"Tagesziel\s*" + RANGE + r"\s*g/kg", text)
        if day:
            out["day"] = (_f(day[1]), _f(day[2] or day[1]))
            text = text[:day.start()]
        for m in re.finditer(grams + r"(\s*(?:pflanzl\w*\s*)?(?:Protein|Eiweiß))?", text):
            key = "protein" if m[3] else "carbs"
            out["after"].setdefault(key, (_f(m[1]), _f(m[2] or m[1])))
    return out


# --- Plan berechnen -----------------------------------------------------------

def _others(workout: dict, workouts: list[dict]) -> list[dict]:
    return [w for w in workouts if w is not workout and (w.get("id") is None or w.get("id") != workout.get("id"))]


def _later_same_day(workout: dict, day_workouts: list[dict]) -> list[tuple[dict, float | None]]:
    """Spätere Einheiten am selben Tag mit Abstand (h) zum Ende dieser Einheit (None = unbekannt)."""
    start = _minutes_of_day(start_time(workout))
    end = start + total_duration(workout.get("steps", [])) / 60 if start is not None else None
    own_index = next((i for i, w in enumerate(day_workouts) if w is workout or
                      (w.get("id") is not None and w.get("id") == workout.get("id"))), len(day_workouts))
    out = []
    for i, other in enumerate(day_workouts):
        if other is workout or (other.get("id") is not None and other.get("id") == workout.get("id")):
            continue
        other_start = _minutes_of_day(start_time(other))
        if end is not None and other_start is not None:
            if other_start >= start:
                out.append((other, max(0.0, (other_start - end) / 60)))
        elif i > own_index:  # ohne Uhrzeiten: Reihenfolge im Kalender
            out.append((other, None))
    return out


def day_target(endurance_hours: float) -> tuple[int, int, str]:
    if endurance_hours <= 0:
        return 3, 5, "Ruhetag / nur Kraft"
    if endurance_hours < 1.75:
        return 5, 7, "moderater Tag"
    if endurance_hours <= 4:
        return 6, 10, "hoher Tag"
    return 8, 12, "sehr hoher Tag"


def plan(workout: dict, settings: dict, day_workouts: list[dict] | None = None,
         next_day_workouts: list[dict] | None = None) -> dict:
    """Verpflegung für eine Einheit. day_workouts = alle Workouts desselben Tages (inkl. dieser Einheit)."""
    day_workouts = day_workouts if day_workouts is not None else [workout]
    next_day_workouts = next_day_workouts or []
    weight_known = bool(settings.get("weight"))
    kg = float(settings.get("weight") or DEFAULT_WEIGHT)
    sweat = float(settings.get("sweat_rate") or 0)  # l/h, 0 = unbekannt
    sport = workout.get("sport")
    kind = classify(workout)
    protein_meal = "Mahlzeit mit pflanzlichem Protein" if settings.get("plant_based") else "Mahlzeit mit Protein"
    seconds = total_duration(workout.get("steps", []))
    hours = seconds / 3600
    day = date.fromisoformat(workout["date"]) if workout.get("date") else date.today()
    weeks = weeks_to_race(day, settings)
    start = start_time(workout)
    start_min = _minutes_of_day(start)
    later = _later_same_day(workout, day_workouts)
    key_within_8h = any(is_key_session(w) and (gap is None or gap < 8) for w, gap in later)
    key_follows = key_within_8h or any(is_key_session(w) for w in _others(workout, next_day_workouts))
    brick_follows = sport == "ride" and any(classify(w) == "brick" for w, _ in later)
    later_ids = {id(w) for w, _ in later}
    ride_before = kind == "brick" and any(w.get("sport") == "ride" and id(w) not in later_ids
                                          for w in _others(workout, day_workouts))
    endurance = sport in ENDURANCE
    parsed = parse_plan(workout.get("description", ""))
    notes: list[str] = []

    # --- vorher
    before: dict = {"carbs": None, "fluid": None, "protein": None, "timing": "", "hint": ""}
    if kind == "brick" and ride_before:
        before["hint"] = "Läuft über die Rad-Verpflegung – direkt nach dem Rad, kein Extra-Essen."
    elif endurance:
        early = start_min is not None and start_min < 9 * 60
        if early:
            lo, hi = 0.5, 1.0
            before["timing"] = f"60–90 min vorher (ca. {_clock(start_min - 90)}–{_clock(start_min - 60)})"
            before["hint"] = "Früher Start: kleines, gut verträgliches Frühstück; am Vorabend KH-betont essen."
        else:
            lo, hi = (2, 3) if sport == "ride" and kind in ("long", "race_pace") else \
                (1, 2) if kind in ("quality", "race_pace") else (1, 1.5)
            before["timing"] = "2–3 h vorher" + (f" (ca. {_clock(start_min - 180)}–{_clock(start_min - 120)})"
                                                 if start_min is not None else "")
        before["carbs"] = _q(lo * kg, hi * kg, "g", (lo, hi))
        if hours >= 1:
            before["fluid"] = _q(5 * kg, 7 * kg, "ml", (5, 7))
            before["fluid_hint"] = "über die Stunden vorher verteilt"
    elif kind == "strength":
        before["hint"] = "Normale Mahlzeit 2–3 h vorher reicht."
    else:
        before["hint"] = "Keine besondere Verpflegung nötig."

    # --- während
    lo, hi, why = during_rate(workout, kind, weeks, key_follows)
    during: dict = {"carbs": _q(lo, hi, "g/h") if endurance else None, "fluid": None, "protein": None,
                    "timing": "", "hint": why, "total": None}
    if endurance and hi:
        during["timing"] = "ab ca. Minute 15–20, kleine Portionen alle 15–20 min"
    if endurance and seconds >= 45 * 60:
        if sweat:
            # Verlust zwischen 1 und 2 % des Körpergewichts halten, nie mehr trinken als ausgeschwitzt wird
            low_ml = max(0.0, sweat - 0.02 * kg / hours) * 1000
            high_ml = max(low_ml, min(sweat, sweat - 0.01 * kg / hours) * 1000)
            during["fluid"] = _q(low_ml, high_ml, "ml/h")
            during["fluid_hint"] = f"aus deiner Schweißrate ({str(sweat).replace('.', ',')} l/h), Ziel < 2 % Gewichtsverlust"
        elif hours >= 1:
            during["fluid"] = _q(400, 800, "ml/h")
            during["fluid_hint"] = "nach Durst"
    # --- danach
    after: dict = {"carbs": None, "fluid": None, "protein": None, "timing": "", "hint": ""}
    if kind == "strength":
        after["protein"] = _q(30, 40, "g")
        after["timing"] = "nächste Mahlzeit, innerhalb von ca. 2 h"
        after["hint"] = f"Normale {protein_meal} – keine Extra-Kohlenhydrate nötig."
    elif endurance:
        if key_within_8h:
            after["carbs"] = _q(1.0 * kg, 1.2 * kg, "g/h", (1.0, 1.2))
            after["protein"] = _q(0.2 * kg, 0.4 * kg, "g/h", (0.2, 0.4))
            after["timing"] = "sofort, stündlich über 4 h"
            after["hint"] = ("Nächste Qualitätseinheit in weniger als 8 h: schnell auffüllen. "
                             "Mit Protein reichen 0,8 g/kg/h Kohlenhydrate.")
        else:
            after["carbs"] = _q(1.0 * kg, 1.5 * kg, "g", (1.0, 1.5))
            after["protein"] = _q(30, 40, "g")
            after["timing"] = "Mahlzeit innerhalb von ca. 1–2 h"
            after["hint"] = f"{protein_meal}."
        if brick_follows:
            after["timing"] = "nach dem Koppellauf"
            after["hint"] = "Direkt Koppellauf – erst danach essen. " + after["hint"]
        if endurance and sweat and seconds >= 45 * 60:
            drunk = (during["fluid"]["low"] + during["fluid"]["high"]) / 2 / 1000 if during["fluid"] else 0
            deficit = max(0.0, (sweat - drunk) * hours)
            if deficit >= 0.2:
                after["fluid"] = _q(1250 * deficit, 1500 * deficit, "ml", None)
                after["fluid_hint"] = "125–150 % des geschätzten Verlusts, über einige Stunden verteilt"
    else:
        after["hint"] = "Keine besondere Verpflegung nötig."

    phases = {"before": before, "during": during, "after": after}
    for key in PHASES:
        phases[key]["source"] = "calc"
        p = parsed.get(key)
        if not p:
            continue
        # Der Plan-Text sagt selbst, wann und warum – berechnete Hinweise würden ihm teils widersprechen
        phases[key].update(plan_text=p["text"], hint="", timing="")
        unit = "g/h" if key == "during" else "g"  # im Plan-Text stehen vorher/danach Gramm
        if "carbs" in p:
            phases[key]["carbs"] = _q(*p["carbs"], unit)
            phases[key]["source"] = "plan"
        if "protein" in p:
            phases[key]["protein"] = _q(*p["protein"], "g")
    if during["carbs"] and seconds:
        c = phases["during"]["carbs"]
        if c["high"]:
            during["total"] = _q(c["low"] * hours, c["high"] * hours, "g")

    rate = phases["during"]["carbs"]["high"] if phases["during"]["carbs"] else 0
    if rate >= 90:
        notes.append("Ab 90 g/h Glukose und Fruktose etwa im Verhältnis 1 : 0,8 kombinieren.")
    elif rate >= 60:
        notes.append("Ab 60 g/h Glukose und Fruktose kombinieren (Mehrfach-Kohlenhydrat-Produkte).")
    if sport == "ride" and kind in ("long", "race_pace") and phases["during"]["source"] == "calc":
        notes.append(_gut_training_rate(weeks)[2])
    if endurance and hours >= 2:
        notes.append("Natrium: Bedarf ist sehr individuell – ein Schweißtest sagt mehr als Pauschalwerte.")
    if endurance and hours >= 1 and not sweat:
        notes.append("Schweißrate unbekannt: einmal vor und nach einer Einheit nackt wiegen (Trinkmenge mitzählen) "
                     "und in den Einstellungen eintragen – dann rechnet die App die Trinkmenge aus.")
    if not weight_known:
        notes.append(f"Kein Gewicht in den Einstellungen – gerechnet mit {DEFAULT_WEIGHT:.0f} kg.")

    endurance_hours = sum(total_duration(w.get("steps", [])) for w in day_workouts
                          if w.get("sport") in ENDURANCE) / 3600
    if workout not in day_workouts and endurance:
        endurance_hours += hours
    d_lo, d_hi, d_label = day_target(endurance_hours)
    if "day" in parsed:
        d_lo, d_hi = parsed["day"]
        d_label = "laut Plan"
    return {
        "weight": kg, "weight_known": weight_known, "sweat_rate": sweat or None,
        "kind": kind, "kind_label": KIND_LABEL[kind], "start": start,
        "end": _clock(start_min + seconds / 60) if start_min is not None and seconds else None,
        "weeks_to_race": round(weeks, 1) if weeks is not None else None,
        "phases": phases,
        "day": {**_q(d_lo * kg, d_hi * kg, "g", (d_lo, d_hi)), "label": d_label,
                "source": "plan" if "day" in parsed else "calc"},
        "notes": notes,
    }


def for_workout(workout: dict, settings: dict, list_workouts) -> dict:
    """Mit Kontext aus der Datenbank: list_workouts(start, end) liefert Workouts (inklusive Enddatum)."""
    if not workout.get("date"):
        return plan(workout, settings)
    day = date.fromisoformat(workout["date"])
    nearby = list_workouts(day.isoformat(), (day + timedelta(days=1)).isoformat())
    same = [w for w in nearby if w["date"] == workout["date"]]
    if not any(w.get("id") is not None and w.get("id") == workout.get("id") for w in same):
        same.append(workout)
    else:  # gespeicherte Version durch die übergebene ersetzen (kann ungespeicherte Änderungen enthalten)
        same = [workout if w.get("id") == workout.get("id") else w for w in same]
    nxt = [w for w in nearby if w["date"] != workout["date"]]
    return plan(workout, settings, same, nxt)

