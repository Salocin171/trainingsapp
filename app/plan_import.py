"""Trainingsplan als JSON importieren (z. B. ein 4-Wochen-Block).

Format (Beispiel: app/static/plan-example.json):

    {
      "name": "Grundlage November",
      "start": "2026-11-02",                 # optional: Montag der 1. Woche, sonst nächster Montag
      "weeks": [
        {"week": 1, "days": {
          "mon": [{"sport": "mobility", "template": "mobility", "minutes": 25}],
          "tue": [{"sport": "ride", "name": "Sweet Spot 3x12", "target": "power", "steps": [
                    {"kind": "warmup", "minutes": 15, "low": 50, "high": 75},
                    {"repeat": 3, "steps": [
                      {"kind": "interval", "minutes": 12, "low": 88, "high": 93},
                      {"kind": "recovery", "minutes": 5, "low": 50, "high": 55}]},
                    {"kind": "cooldown", "minutes": 10, "low": 50, "high": 65}]}]
        }}
      ]
    }

- Tage: mon…sun, Mo…So oder Montag…Sonntag. Pro Tag beliebig viele Workouts.
- Alternativ hat ein Workout ein festes "date": "2026-11-05".
- Ein Workout hat entweder "steps" oder "template" + "minutes" (Vorlagen aus templates.py).
- Schritte: "kind" (warmup | interval | recovery | steady | cooldown), Dauer als "minutes" oder
  "seconds", Intensität "low"/"high" in % (FTP / Schwellentempo bzw. CSS / LTHR je nach "target").
  Wiederholung: {"repeat": 4, "steps": [...]}. Optional je Schritt "target" (power | pace | hr), wenn er anders
  gesteuert wird als das Workout – z. B. Einlaufen nach Puls, Intervalle nach Pace.
- Kurzform (spart viel Text, z. B. für KI-Pläne): "steps": "w15@50-75, 4x(i8@97-102, r4@50-55), c10@50-65"
  w/i/r/s/c = warmup/interval/recovery/steady/cooldown, Zahl = Minuten (Suffix s = Sekunden), @von-bis in %,
  danach optional hr / pace / power für ein eigenes Ziel des Schritts ("w15@70-80hr").
- "time": "08:00" → Startzeit (steht dann vorne im Namen, daraus rechnet die Ernährung den Zeitpunkt).
- "fueling": {"before": "…", "during": "90 g/h", "after": "…", "day": "6–10 g/kg"} → KH-Block in der Beschreibung.
  Ohne "fueling" berechnet die App die Ernährung selbst (app/nutrition.py).
- Kraft/Stabi optional mit Zirkel-Timer: "circuit": {"work": 40, "rest": 20, "rounds": 3, "round_rest": 60,
  "exercises": ["Plank", "Rudern mit Band | 12 Wdh", {"name": "Wandsitz", "seconds": 45}]} – Sekunden,
  Runde = einmal alle Übungen. Übung ohne Angabe dauert "work"; mit Wiederholungen geht es per „Fertig“ weiter
  ("reps": 0 = ohne feste Zahl, z. B. bis kurz vor Versagen).
"""
import re
from datetime import date, timedelta

from . import templates
from .periodization import monday
from .workouts import SPORTS, STEP_KINDS, TARGETS, repeat, step

DAY_NAMES = {
    0: ("mon", "mo", "montag", "monday"), 1: ("tue", "di", "dienstag", "tuesday"),
    2: ("wed", "mi", "mittwoch", "wednesday"), 3: ("thu", "do", "donnerstag", "thursday"),
    4: ("fri", "fr", "freitag", "friday"), 5: ("sat", "sa", "samstag", "saturday"),
    6: ("sun", "so", "sonntag", "sunday"),
}
DAY_INDEX = {name: i for i, names in DAY_NAMES.items() for name in names}
# Bekannte Felder – alles andere wird in der Vorschau als Warnung gemeldet statt still verworfen
PLAN_KEYS = {"name", "start", "weeks", "workouts", "description"}
WEEK_KEYS = {"week", "days", "name", "description"}
WORKOUT_KEYS = {"sport", "name", "description", "target", "steps", "template", "minutes", "circuit", "date", "time",
                "fueling"}
STEP_KEYS = {"kind", "minutes", "seconds", "duration", "low", "high", "target"}
REPEAT_KEYS = {"repeat", "count", "kind", "steps"}
FUEL_KEYS = {"before": "Vorher", "during": "Während", "after": "Danach", "day": "Tagesziel"}
KIND_LETTERS = {"w": "warmup", "i": "interval", "r": "recovery", "s": "steady", "c": "cooldown"}
COMPACT_STEP = re.compile(r"([wirsc])\s*(\d+(?:[.,]\d+)?)\s*(s|sek|m|min)?\s*(?:@\s*(\d+(?:[.,]\d+)?)"
                          r"(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*%?\s*(hr|hf|puls|pace|power|watt)?)?", re.I)
COMPACT_TARGETS = {"hr": "hr", "hf": "hr", "puls": "hr", "pace": "pace", "power": "power", "watt": "power"}


class PlanError(ValueError):
    pass


def default_start(today: date) -> date:
    """Nächster Montag (heute, falls heute Montag ist)."""
    return monday(today) if today.weekday() == 0 else monday(today) + timedelta(weeks=1)


def _number(value, where: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise PlanError(f"{where}: Zahl erwartet, bekommen: {value!r}") from None


def _split_top(text: str) -> list[str]:
    """Kommagetrennte Teile, Kommas in Klammern bleiben drin."""
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch in ",;" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def compact_steps(text: str, where: str) -> list[dict]:
    """Kurzform "w15@50-75, 4x(i8@97-102, r4@50-55), c10" → Schritte im Plan-Format."""
    out = []
    for part in _split_top(text):
        m = re.fullmatch(r"(\d+)\s*[x×]\s*[(\[](.*)[)\]]", part, re.S)
        if m:
            out.append({"repeat": int(m[1]), "steps": compact_steps(m[2], where)})
            continue
        m = COMPACT_STEP.fullmatch(part)
        if not m:
            raise PlanError(f"{where}: Schritt {part!r} nicht verstanden – Form z. B. 'i8@97-102' oder '4x(i4@110, r4@50)'")
        amount = float(m[2].replace(",", "."))
        low = float(m[4].replace(",", ".")) if m[4] else 0
        high = float(m[5].replace(",", ".")) if m[5] else low
        unit = "seconds" if (m[3] or "").lower() in ("s", "sek") else "minutes"
        out.append({"kind": KIND_LETTERS[m[1].lower()], unit: amount, "low": low, "high": high,
                    **({"target": COMPACT_TARGETS[m[6].lower()]} if m[6] else {})})
    if not out:
        raise PlanError(f"{where}: 'steps' ist leer")
    return out


def _steps(raw: list | str, where: str) -> list[dict]:
    if isinstance(raw, str):
        raw = compact_steps(raw, where)
    if not isinstance(raw, list) or not raw:
        raise PlanError(f"{where}: 'steps' muss eine nicht-leere Liste sein")
    out = []
    for i, s in enumerate(raw, 1):
        here = f"{where}, Schritt {i}"
        if not isinstance(s, dict):
            raise PlanError(f"{here}: Objekt erwartet")
        is_repeat = "repeat" in s or s.get("kind") == "repeat"
        # Unbekannte Felder nicht still verwerfen – sonst landet z. B. ein falsch benanntes Ziel als Puls auf der Uhr
        unknown = sorted(k for k in s if k not in (REPEAT_KEYS if is_repeat else STEP_KEYS))
        if unknown:
            hint = " – eigenes Ziel des Schritts heißt 'target' (power | pace | hr)" if not is_repeat else ""
            raise PlanError(f"{here}: unbekannte Felder {', '.join(map(repr, unknown))}{hint}")
        if is_repeat:
            count = int(_number(s.get("repeat", s.get("count")), here))
            if count < 1:
                raise PlanError(f"{here}: Wiederholungen müssen ≥ 1 sein")
            out.append(repeat(count, *_steps(s.get("steps"), f"{here} (Wiederholung)")))
            continue
        kind = s.get("kind", "steady")
        if kind not in STEP_KINDS:
            raise PlanError(f"{here}: unbekannter Schritt {kind!r} (erlaubt: {', '.join(STEP_KINDS)})")
        if "minutes" in s:
            minutes = _number(s["minutes"], here)
        elif "seconds" in s or "duration" in s:
            minutes = _number(s.get("seconds", s.get("duration")), here) / 60
        else:
            raise PlanError(f"{here}: Dauer fehlt ('minutes' oder 'seconds')")
        if minutes <= 0:
            raise PlanError(f"{here}: Dauer muss > 0 sein")
        low = _number(s.get("low", 0), here)
        high = _number(s.get("high", low), here)
        target = s.get("target")
        if target not in (None, "", *TARGETS):
            raise PlanError(f"{here}: unbekanntes Ziel {target!r} (erlaubt: {', '.join(TARGETS)})")
        out.append(step(kind, minutes, low, high) | ({"target": target} if target else {}))
    return out


# Zirkel-Timer: Feld → (min, max)
CIRCUIT_LIMITS = {"work": (5, 600), "rest": (0, 600), "rounds": (1, 60), "round_rest": (0, 900)}
EXERCISE_LIMITS = {"reps": (0, 200), "seconds": (5, 600)}
# Kurzform hinter dem letzten „|“: „12 Wdh“ / „Wdh“ (ohne Zahl) bzw. „45 s“ – gleiche Regeln in static/js/timer.js
REPS_TEXT = re.compile(r"(\d*)\s*(wdh\.?|wiederholungen|reps?|x)", re.I)
SECONDS_TEXT = re.compile(r"(\d+)\s*(s|sek\.?|sekunden)", re.I)


def parse_exercise(raw, where: str) -> dict | None:
    """Eine Zirkel-Übung → {"name", "reps"?, "seconds"?}; leerer Name → None."""
    if not isinstance(raw, dict):
        name, bar, tail = str(raw).rpartition("|")
        reps, secs = REPS_TEXT.fullmatch(tail.strip()), SECONDS_TEXT.fullmatch(tail.strip())
        if not bar or not (reps or secs):
            name = str(raw)
        raw = {"name": name, **({"reps": reps[1] or 0} if bar and reps else {}),
               **({"seconds": secs[1]} if bar and secs else {})}
    out = {"name": str(raw.get("name", "")).strip()[:80]}
    for key, (lo, hi) in EXERCISE_LIMITS.items():
        if raw.get(key) is None or (key == "seconds" and "reps" in out):
            continue
        value = int(_number(raw[key], f"{where}.{key}"))
        if not lo <= value <= hi:
            raise PlanError(f"{where}.{key}: {value} liegt nicht zwischen {lo} und {hi}")
        out[key] = value
    return out if out["name"] else None


def parse_circuit(raw, where: str) -> dict:
    where = f"{where}, circuit"
    if not isinstance(raw, dict):
        raise PlanError(f"{where}: Objekt erwartet")
    out = {}
    for key, (lo, hi) in CIRCUIT_LIMITS.items():
        value = int(_number(raw.get(key, templates.STABI_CIRCUIT.get(key, 1)), f"{where}.{key}"))
        if not lo <= value <= hi:
            raise PlanError(f"{where}.{key}: {value} liegt nicht zwischen {lo} und {hi}")
        out[key] = value
    exercises = raw.get("exercises", [])
    if not isinstance(exercises, list):
        raise PlanError(f"{where}.exercises: Liste von Übungen erwartet")
    parsed = (parse_exercise(e, f"{where}.exercises[{i}]") for i, e in enumerate(exercises, 1))
    out["exercises"] = [e for e in parsed if e][:30]
    return out


def _unknown(raw: dict, known: set, where: str, warnings: list | None) -> None:
    if warnings is not None:
        warnings += [f"{where}: Feld {k!r} unbekannt – ignoriert" for k in raw if k not in known]


def fueling_block(raw, where: str, warnings: list | None = None) -> str:
    """"fueling" → KH-Block im Format, das app/nutrition.py in der Beschreibung liest."""
    if isinstance(raw, str):
        raw = {"during": raw}
    if not isinstance(raw, dict):
        raise PlanError(f"{where}: 'fueling' muss ein Objekt sein, z. B. {{\"during\": \"90 g/h\"}}")
    _unknown(raw, set(FUEL_KEYS), f"{where}, fueling", warnings)
    text = {k: str(raw[k]).strip().rstrip(".") for k in FUEL_KEYS if str(raw.get(k) or "").strip()}
    if "day" in text:  # das Tagesziel steht in der Danach-Zeile
        day = text.pop("day")
        day = day if day.lower().startswith("tagesziel") else f"Tagesziel {day}"
        text["after"] = f"{text['after']}; {day}" if "after" in text else day
    lines = [f"- {FUEL_KEYS[k]}: {v}." for k, v in text.items()]
    return "KH:\n" + "\n".join(lines) if lines else ""


def _workout(raw: dict, day: date, where: str, warnings: list | None = None) -> dict:
    if not isinstance(raw, dict):
        raise PlanError(f"{where}: Workout-Objekt erwartet")
    _unknown(raw, WORKOUT_KEYS, where, warnings)
    sport = raw.get("sport", "ride")
    if sport not in SPORTS:
        raise PlanError(f"{where}: unbekannter Sport {sport!r} (erlaubt: {', '.join(SPORTS)})")
    if "steps" in raw:
        workout = {"sport": sport, "name": "Workout", "description": "", "template": "",
                   "target": templates.default_target(sport), "steps": _steps(raw["steps"], where)}
    elif "template" in raw:
        kind = raw["template"]
        if kind not in templates.TEMPLATES:
            raise PlanError(f"{where}: unbekannte Vorlage {kind!r} (erlaubt: {', '.join(templates.TEMPLATES)})")
        workout = templates.build(kind, sport, int(_number(raw.get("minutes", 60), where)))
    else:
        raise PlanError(f"{where}: 'steps' oder 'template' fehlt")
    target = raw.get("target", workout["target"])
    if target not in TARGETS:
        raise PlanError(f"{where}: unbekanntes Ziel {target!r} (erlaubt: {', '.join(TARGETS)})")
    if "circuit" in raw:
        workout["circuit"] = parse_circuit(raw["circuit"], where)
    name = str(raw.get("name") or workout["name"]).strip()
    if raw.get("time"):
        m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", str(raw["time"]).strip())
        if not m or int(m[1]) > 23 or int(m[2]) > 59:
            raise PlanError(f"{where}: 'time' muss eine Uhrzeit wie \"07:30\" sein")
        if not re.match(r"\s*\d{1,2}[:.]\d{2}\b", name):  # Startzeit steht vorne im Namen (so liest sie die App)
            name = f"{int(m[1]):02d}:{m[2]} · {name}"
    description = str(raw.get("description", workout["description"])).strip()
    if raw.get("fueling"):
        block = fueling_block(raw["fueling"], where, warnings)
        description = f"{description}\n\n{block}".strip() if block else description
    return {
        **workout, "date": day.isoformat(), "target": target, "status": "planned",
        "name": name[:120], "description": description,
    }


def build_workout(raw: dict, day: date) -> dict:
    """Ein einzelnes Workout im Plan-Format (steps in Minuten oder template + minutes) → Workout-Dict."""
    return _workout(raw, day, "Workout")


def parse(plan: dict, today: date, start: str | None = None,
          warnings: list | None = None) -> tuple[list[dict], date, date]:
    """Plan → Liste von Workouts mit Datum. Wirft PlanError mit verständlicher Meldung.
    warnings (Liste) sammelt Hinweise, z. B. auf unbekannte Felder."""
    if not isinstance(plan, dict):
        raise PlanError("Der Plan muss ein JSON-Objekt sein ({ ... })")
    _unknown(plan, PLAN_KEYS, "Plan", warnings)
    try:
        first = monday(date.fromisoformat(start or plan.get("start") or default_start(today).isoformat()))
    except ValueError:
        raise PlanError("'start' muss ein Datum im Format JJJJ-MM-TT sein") from None
    source = str(plan.get("name") or "Plan-Import")

    workouts = []
    for wi, week in enumerate(plan.get("weeks") or [], 1):
        number = int(_number(week.get("week", wi), f"Woche {wi}"))
        _unknown(week, WEEK_KEYS, f"Woche {number}", warnings)
        if number < 1:
            raise PlanError(f"Woche {wi}: 'week' muss ≥ 1 sein")
        for day_name, items in (week.get("days") or {}).items():
            index = DAY_INDEX.get(str(day_name).strip().lower())
            if index is None:
                raise PlanError(f"Woche {number}: unbekannter Tag {day_name!r} (z. B. mon, Di, Mittwoch)")
            day = first + timedelta(weeks=number - 1, days=index)
            for ii, raw in enumerate(items if isinstance(items, list) else [items], 1):
                workouts.append(_workout(raw, day, f"Woche {number} {DAY_NAMES[index][1].title()}, Workout {ii}",
                                         warnings))
    for ii, raw in enumerate(plan.get("workouts") or [], 1):  # Workouts mit festem Datum
        try:
            day = date.fromisoformat(raw["date"])
        except (KeyError, TypeError, ValueError):
            raise PlanError(f"workouts[{ii}]: 'date' fehlt oder ist kein Datum (JJJJ-MM-TT)") from None
        workouts.append(_workout(raw, day, f"workouts[{ii}] ({raw['date']})", warnings))

    if not workouts:
        raise PlanError("Keine Workouts gefunden – erwartet wird 'weeks' (mit 'days') oder 'workouts'")
    workouts.sort(key=lambda w: w["date"])
    for w in workouts:
        w["source"] = source
    return workouts, date.fromisoformat(workouts[0]["date"]), date.fromisoformat(workouts[-1]["date"])
