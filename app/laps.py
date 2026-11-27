"""Abschnitte einer erledigten Einheit: Zwischenzeiten, Puls, Pace/Leistung je Intervall – mit Ziel aus dem Plan.

Drei Wege, je nachdem, was Garmin liefert:
    steps  Workout lief auf der Uhr: Runden tragen den Workout-Schritt (wktStepIndex). Runden desselben Schritts
           werden zusammengefasst (z. B. 1000 m Auto-Runde + Rest), jeder Abschnitt bekommt sein Ziel aus dem Plan.
    plan   Keine Schritt-Runden, aber ein zugeordnetes Workout (typisch Rolle mit Zwift/ERG): der Verlauf wird nach
           den geplanten Schrittdauern ab Start der Aufzeichnung geschnitten.
    laps   Sonst die Runden, wie sie sind (Auto-Runden pro km, Schwimmserien mit Pausen).

Reine Funktionen ohne Datenbank und Netz; Runden/Verlauf kommen aus sync/garmin.parse_laps bzw. parse_stream.
"""
from .workouts import step_target

TARGET_TOLERANCE = 0.02  # 2 % Spielraum, bevor ein Abschnitt als „außerhalb“ gilt
RATED_KINDS = ("interval", "steady")  # Pausen, Ein- und Auslaufen dürfen lockerer sein – dort keine Bewertung
STEP_COVERAGE = 0.8  # so viel der Zeit müssen Runden mit Workout-Schritt abdecken (sonst lief das Workout nicht mit)
PLAN_CUT_SPORTS = ("ride",)  # Rolle: Workouts laufen exakt nach Zeit; Laufen/Schwimmen weichen davon ab


def fit_steps(steps: list[dict]) -> list[dict | None]:
    """Workout-Schritte in der Nummerierung der Uhr (FIT): Wiederholungen erst ihre Schritte, dann die Gruppe selbst.
    Index = wktStepIndex der Runden; None = Wiederholungsgruppe (kommt in Runden nicht vor)."""
    out: list[dict | None] = []
    for s in steps:
        if s.get("kind") == "repeat":
            out += fit_steps(s.get("steps", []))
            out.append(None)
        else:
            out.append(s)
    return out


def _leaf_steps(steps: list[dict]) -> list[tuple[dict, int]]:
    """Geplante Schritte in Ausführungsreihenfolge mit ihrem FIT-Index (zum Gruppieren gleicher Intervalle)."""
    index = {id(s): i for i, s in enumerate(fit_steps(steps)) if s is not None}
    out = []

    def walk(items):
        for s in items:
            if s.get("kind") == "repeat":
                for _ in range(int(s.get("count", 1))):
                    walk(s.get("steps", []))
            else:
                out.append((s, index[id(s)]))
    walk(steps)
    return out


def threshold_speed(sport: str, settings: dict) -> float:
    """m/s an der Schwelle: CSS beim Schwimmen, Schwellentempo beim Laufen (wie sync/garmin)."""
    if sport == "swim":
        return 100 / settings["css"] if settings.get("css") else 0
    return 1000 / settings["threshold_pace"] if settings.get("threshold_pace") else 0


def target_range(step: dict | None, workout: dict, settings: dict) -> dict | None:
    """Zielbereich eines geplanten Schritts in echten Einheiten: power (W), hr (bpm) oder pace (Geschwindigkeit m/s)."""
    if not step:
        return None
    sport = workout.get("sport")
    low, high = float(step.get("low", 0)) / 100, float(step.get("high", step.get("low", 0))) / 100
    if not low or sport not in ("swim", "ride", "run"):
        return None
    kind = step_target(workout, step)
    if kind == "power":
        base = settings.get("ftp") or 0
    elif kind == "hr":
        base = settings.get("lthr_ride" if sport == "ride" else "lthr_run") or 0
    else:
        kind, base = "pace", threshold_speed(sport, settings)
    return {"type": kind, "low": round(low * base, 3), "high": round(high * base, 3)} if base else None


def _value_for(segment: dict, kind: str):
    return {"power": segment.get("power"), "hr": segment.get("hr"), "pace": segment.get("speed")}.get(kind)


def in_target(segment: dict, target: dict | None) -> bool | None:
    value = _value_for(segment, target["type"]) if target else None
    if not value:
        return None
    return target["low"] * (1 - TARGET_TOLERANCE) <= value <= target["high"] * (1 + TARGET_TOLERANCE)


def _weighted(parts: list[dict], key: str) -> float | None:
    """Zeitgewichteter Mittelwert (Puls, Leistung, Kadenz) über Runden."""
    pairs = [(p[key], p.get("duration") or 0) for p in parts if p.get(key)]
    seconds = sum(d for _, d in pairs)
    return round(sum(v * d for v, d in pairs) / seconds, 1) if seconds else None


def combine(parts: list[dict]) -> dict:
    """Mehrere Runden zu einem Abschnitt: Summen für Zeit/Strecke, zeitgewichtete Mittel, Maxima."""
    duration = sum(p.get("duration") or 0 for p in parts)
    distance = sum(p.get("distance") or 0 for p in parts)
    out = {
        "start": parts[0].get("start"), "duration": round(duration, 1), "distance": round(distance, 1),
        "speed": round(distance / duration, 3) if distance and duration else None,
        "gap": _weighted(parts, "gap"), "hr": _weighted(parts, "hr"),
        "max_hr": max((p["max_hr"] for p in parts if p.get("max_hr")), default=None),
        "power": _weighted(parts, "power"), "cadence": _weighted(parts, "cadence"),
        # NP lässt sich aus Runden nicht exakt mitteln – nur bei einer einzelnen Runde übernehmen
        "np": parts[0].get("np") if len(parts) == 1 else None,
        "swolf": _weighted(parts, "swolf"),
        "strokes": sum(p["strokes"] for p in parts if p.get("strokes")) or None,
        "stroke": parts[0].get("stroke"),
    }
    return {k: v for k, v in out.items() if v is not None}


def _from_steps(laps: list[dict], workout: dict | None) -> list[dict]:
    """Runden mit Workout-Schritt: aufeinanderfolgende Runden desselben Schritts zusammenfassen."""
    plan = fit_steps(workout.get("steps", [])) if workout else []
    groups: list[list[dict]] = []
    for lap in laps:
        if groups and groups[-1][-1].get("step") == lap.get("step") and groups[-1][-1].get("kind") == lap.get("kind"):
            groups[-1].append(lap)
        else:
            groups.append([lap])
    segments = []
    for g in groups:
        step_index = g[0].get("step")
        planned = plan[step_index] if step_index is not None and 0 <= step_index < len(plan) else None
        segments.append({**combine(g), "kind": g[0].get("kind") or (planned or {}).get("kind"), "group": step_index,
                         "laps": len(g), "planned": planned})
    return segments


def _from_plan(stream: dict, workout: dict) -> list[dict]:
    """Verlauf nach den geplanten Schrittdauern schneiden (ab Start der Aufzeichnung)."""
    t = stream["t"]
    end = t[-1] if t else 0
    segments, start = [], 0.0
    for step, group in _leaf_steps(workout.get("steps", [])):
        stop = start + float(step.get("duration", 0))
        if start >= end:
            break
        idx = [i for i, x in enumerate(t) if start <= x < stop]
        if idx:
            def avg(key):
                values = [stream[key][i] for i in idx if key in stream and stream[key][i]]
                return round(sum(values) / len(values), 1) if values else None
            duration = min(stop, end) - start
            dist = stream.get("distance")
            distance = (dist[idx[-1]] or 0) - (dist[idx[0]] or 0) if dist else 0
            seg = {"start": round(start), "duration": round(duration, 1), "distance": round(distance, 1),
                   "speed": round(distance / duration, 3) if distance and duration else None,
                   "hr": avg("hr"), "power": avg("power"), "cadence": avg("cadence"),
                   "max_hr": max((stream["hr"][i] for i in idx if "hr" in stream and stream["hr"][i]), default=None)}
            segments.append({**{k: v for k, v in seg.items() if v is not None},
                             "kind": step.get("kind"), "group": group, "laps": 1, "planned": step})
        start = stop
    return segments


def _group_swim_sets(segments: list[dict]) -> None:
    """Schwimmen ohne Workout auf der Uhr: aufeinanderfolgende Serien gleicher Länge (Pausen dazwischen erlaubt)
    bilden eine Gruppe, z. B. 8 × 100 m."""
    group, last = 0, None
    for s in segments:
        if s.get("kind") == "rest":
            continue
        if s.get("distance") != last:
            group, last = group + 1, s.get("distance")
        s["group"] = group


def _number_repeats(segments: list[dict]) -> None:
    """Gleiche Intervalle durchzählen: „2/5“."""
    totals: dict = {}
    for s in segments:
        if s.get("group") is not None:
            totals[s["group"]] = totals.get(s["group"], 0) + 1
    seen: dict = {}
    for s in segments:
        g = s.get("group")
        if g is not None and totals[g] > 1:
            seen[g] = seen.get(g, 0) + 1
            s["rep"] = f"{seen[g]}/{totals[g]}"


def _interval_summaries(segments: list[dict]) -> list[dict]:
    """Je Intervall-Gruppe (z. B. 5 × 1000 m): Mittelwerte und wie viele im Zielbereich lagen."""
    groups: dict = {}
    for s in segments:
        if s.get("kind") in ("interval", None) and s.get("group") is not None:
            groups.setdefault(s["group"], []).append(s)
    out = []
    for group in groups.values():
        if len(group) < 2:
            continue
        rated = [s["in_target"] for s in group if s.get("in_target") is not None]
        out.append({**combine(group), "count": len(group), "avg_duration": round(sum(s["duration"] for s in group) / len(group)),
                    "avg_distance": round(sum(s.get("distance") or 0 for s in group) / len(group)),
                    "target": group[0].get("target"), "in_target": sum(rated), "rated": len(rated)})
    return out


def build(activity: dict, laps: list[dict], stream: dict | None, workout: dict | None, settings: dict) -> dict:
    """Abschnitte, Intervall-Zusammenfassung und Gesamtwerte einer Aktivität (siehe Moduldoku)."""
    sport = activity.get("sport")
    total_seconds = sum(lap.get("duration") or 0 for lap in laps)
    step_seconds = sum(lap.get("duration") or 0 for lap in laps if lap.get("step") is not None)
    if total_seconds and step_seconds >= STEP_COVERAGE * total_seconds:
        source, segments = "steps", _from_steps(laps, workout)
    elif workout and stream and sport in PLAN_CUT_SPORTS and len(_leaf_steps(workout.get("steps", []))) > 1:
        source, segments = "plan", _from_plan(stream, workout)
    else:
        source, segments = "laps", [{**lap, "laps": 1} for lap in laps]
    for s in segments:
        planned = s.pop("planned", None)
        if workout and planned:
            s["target"] = target_range(planned, workout, settings)
            if s.get("kind") in RATED_KINDS:
                s["in_target"] = in_target(s, s["target"])
        s.pop("step", None)
    if source == "laps" and sport == "swim":
        _group_swim_sets(segments)
    _number_repeats(segments)
    total = combine(laps) if laps else {}
    m = activity.get("metrics") or {}
    total.update({k: v for k, v in (("hr", m.get("avg_hr")), ("max_hr", m.get("max_hr")), ("np", m.get("np")),
                                    ("power", m.get("avg_power"))) if v})
    if activity.get("distance") and activity.get("duration"):
        total.update(distance=round(activity["distance"], 1), duration=activity["duration"],
                     speed=round(activity["distance"] / activity["duration"], 3))
    return {
        "source": source, "sport": sport, "segments": segments, "intervals": _interval_summaries(segments),
        "laps": laps if source != "laps" and len(laps) > 1 else [], "total": total,
        "workout": {"id": workout["id"], "name": workout.get("name")} if workout and workout.get("id") else None,
    }
