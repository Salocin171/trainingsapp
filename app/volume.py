"""Umfang: Wochenstunden (Soll / erledigt / geplant) und eigene Ziele in Stunden oder Kilometern.

Wochenstunden = Schwimmen + Rad + Laufen. Stabi, Dehnen usw. werden getrennt als "extra" gezählt.

Erledigt = importierte Aktivitäten plus als erledigt markierte Workouts, für die es am selben Tag
keine importierte Aktivität derselben Sportart gibt (sonst würde doppelt gezählt).
Kilometer gibt es für Ziele nur aus importierten Aktivitäten. Die Wochenübersicht (week_summary) schätzt die
Strecke geplanter Workouts zusätzlich aus Name bzw. Tempo-Zielen.
"""
from calendar import monthrange
from datetime import date, timedelta

from . import periodization
from .feedback import activity_intensity
from .load import form_label
from .templates import ENDURANCE_SPORTS, is_hard
from .workouts import estimate_distance, estimate_tss, flatten, total_duration

GOAL_PERIODS = {"week": "diese Woche", "month": "diesen Monat", "year": "dieses Jahr", "custom": "Zeitraum"}
GOAL_METRICS = {"hours": "h", "km": "km"}


def done_items(activities: list[dict], workouts: list[dict]) -> list[dict]:
    """Erledigte Einheiten als {date, sport, seconds, meters}."""
    items = [{"date": a["date"], "sport": a["sport"], "seconds": a.get("duration") or 0,
              "meters": a.get("distance") or 0} for a in activities]
    imported = {(a["date"], a["sport"]) for a in activities}
    for w in workouts:
        if w.get("status") == "done" and (w["date"], w.get("sport")) not in imported:
            items.append({"date": w["date"], "sport": w.get("sport"), "seconds": total_duration(w.get("steps", [])),
                          "meters": 0})
    return items


def planned_items(workouts: list[dict], today: date) -> list[dict]:
    return [{"date": w["date"], "sport": w.get("sport"), "seconds": total_duration(w.get("steps", []))}
            for w in workouts if w.get("status") != "done" and w["date"] >= today.isoformat()]


def weeks(settings: dict, activities: list[dict], workouts: list[dict], today: date,
          before: int = 3, after: int = 2) -> list[dict]:
    """Wochenübersicht von `before` Wochen zurück bis `after` Wochen voraus."""
    done, planned = done_items(activities, workouts), planned_items(workouts, today)
    out = []
    for i in range(-before, after + 1):
        start = periodization.monday(today) + timedelta(weeks=i)
        end = (start + timedelta(days=6)).isoformat()
        info = periodization.week_info(settings, start)
        by_sport: dict[str, dict] = {}
        for key, items in (("done", done), ("planned", planned)):
            for it in items:
                if start.isoformat() <= it["date"] <= end:
                    entry = by_sport.setdefault(it["sport"] or "other", {"done": 0.0, "planned": 0.0})
                    entry[key] += it["seconds"] / 3600
        endurance = [v for k, v in by_sport.items() if k in ENDURANCE_SPORTS]
        extra = [v for k, v in by_sport.items() if k not in ENDURANCE_SPORTS]
        out.append({
            "week_start": start.isoformat(), "current": i == 0,
            "target_hours": info["target_hours"], "block_name": info["block_name"], "recovery": info["recovery"],
            "block": info["block"], "cycle_week": info["cycle_week"], "cycle_no": info["cycle_no"],
            "cycle_color": info["cycle_color"],
            "done_hours": round(sum(s["done"] for s in endurance), 1),
            "planned_hours": round(sum(s["planned"] for s in endurance), 1),
            "extra_hours": round(sum(s["done"] + s["planned"] for s in extra), 1),
            "by_sport": {k: {"done": round(v["done"], 1), "planned": round(v["planned"], 1)} for k, v in by_sport.items()},
        })
    return out


def period_range(goal: dict, today: date) -> tuple[date, date]:
    period = goal.get("period", "week")
    if period == "week":
        start = periodization.monday(today)
        return start, start + timedelta(days=6)
    if period == "month":
        return today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1])
    if period == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    return date.fromisoformat(goal["start"]), date.fromisoformat(goal["end"])


def goal_progress(goal: dict, activities: list[dict], workouts: list[dict], today: date) -> dict:
    """Fortschritt eines Ziels. `expected` = Anteil, den man bei gleichmäßigem Training heute hätte."""
    start, end = period_range(goal, today)
    in_range = lambda it: start.isoformat() <= it["date"] <= end.isoformat()  # noqa: E731
    sport = goal.get("sport", "all")
    match = lambda it: sport == "all" or it["sport"] == sport  # noqa: E731
    done = [it for it in done_items(activities, workouts) if in_range(it) and match(it)]
    planned = [it for it in planned_items(workouts, today) if in_range(it) and match(it)]
    if goal.get("metric") == "km":
        value, planned_value = sum(it["meters"] for it in done) / 1000, None
    else:
        value = sum(it["seconds"] for it in done) / 3600
        planned_value = round(sum(it["seconds"] for it in planned) / 3600, 1)
    target = float(goal.get("target") or 0)
    total_days = (end - start).days + 1
    elapsed = min(total_days, max(0, (today - start).days + 1))
    return {
        **goal, "start": start.isoformat(), "end": end.isoformat(),
        "value": round(value, 1), "planned": planned_value,
        "pct": round(value / target * 100) if target else 0,
        "expected": round(elapsed / total_days * 100),
    }


# --- Wochenübersicht (Wochenansicht des Kalenders) -----------------------------

# Grenzen in % der Schwelle: (locker unter, hart ab). Dazwischen Zone 3 (mittel).
# Schwimmen in % der CSS-Geschwindigkeit – ruhige Bahnen liegen schon bei 85–95 %, hart ist erst CSS-Tempo.
INTENSITY_LIMITS = {"swim": (85, 98)}
DEFAULT_LIMITS = (76, 88)   # Rad/Laufen; 88 % wie compliance.HARD_PCT (Sweet Spot zählt als hart)
HARD_MIN_SECONDS = 600      # so viel Zeit über der Hart-Grenze macht eine Einheit zur harten Einheit
EASY_STEPS = ("warmup", "cooldown", "recovery")


def _intensity_from_steps(workout: dict) -> tuple[dict, int]:
    """→ (Sekunden locker/mittel/hart, Sekunden hart ohne Ein-/Ausfahren und Pausen)."""
    easy_below, hard_from = INTENSITY_LIMITS.get(workout.get("sport"), DEFAULT_LIMITS)
    out, hard_work = {"easy": 0, "moderate": 0, "hard": 0}, 0
    for s in flatten(workout.get("steps", [])):
        pct = (float(s.get("low", 0)) + float(s.get("high", s.get("low", 0)))) / 2
        if pct <= 0:  # 0 % = Pause
            continue
        level = "easy" if pct < easy_below else "hard" if pct >= hard_from else "moderate"
        out[level] += s.get("duration", 0)
        if level == "hard" and s.get("kind") not in EASY_STEPS:
            hard_work += s.get("duration", 0)
    return out, hard_work


def _intensity_from_zones(zones: list) -> dict:
    """Pulszonen 1–5 → locker (1–2), mittel (3), hart (4–5)."""
    z = list(zones) + [0] * (5 - len(zones))
    return {"easy": z[0] + z[1], "moderate": z[2], "hard": z[3] + z[4]}


def _activity_item(a: dict) -> dict:
    zones = (a.get("metrics") or {}).get("hr_zones")
    intensity = _intensity_from_zones(zones) if zones and sum(zones) else None
    hard = activity_intensity(a)[1] or bool(intensity and intensity["hard"] >= HARD_MIN_SECONDS)
    return {"date": a["date"], "sport": a.get("sport") or "other", "name": a.get("name") or "", "done": True,
            "seconds": a.get("duration") or 0, "meters": a.get("distance") or 0, "estimated": False,
            "tss": float(a.get("tss") or 0), "hard": hard, "intensity": intensity}


def _workout_item(w: dict, settings: dict, done: bool) -> dict:
    meters = estimate_distance(w, settings) if w.get("sport") in ENDURANCE_SPORTS else 0
    tss = w["actual_tss"] if done and w.get("actual_tss") is not None else estimate_tss(w)
    intensity, hard_work = _intensity_from_steps(w)
    return {"date": w["date"], "sport": w.get("sport") or "other", "name": w.get("name") or "", "done": done,
            "seconds": total_duration(w.get("steps", [])), "meters": meters, "estimated": bool(meters),
            "tss": float(tss), "hard": is_hard(w.get("template", "")) or hard_work >= HARD_MIN_SECONDS,
            "intensity": intensity}


def _load_end(load: dict | None) -> dict | None:
    """Fitness, Ermüdung und Form nach dem letzten Tag der Woche (Form = CTL − ATL, gerundet wie angezeigt)."""
    if not load:
        return None
    ctl, atl = round(load["ctl"]), round(load["atl"])
    return {"ctl": ctl, "atl": atl, "tsb": ctl - atl, "form": form_label(ctl - atl)}


def week_summary(settings: dict, monday: date, activities: list[dict], workouts: list[dict], today: date,
                 load: dict | None = None) -> dict:
    """Statistik einer Woche: Erledigtes mit echten Werten, noch Geplantes geschätzt; verpasste Workouts nur gezählt.

    workouts: per compliance.mark_matched markiert (per Aktivität erledigte gelten als erledigt).
    load: Belastung am Ende der Woche ({ctl, atl}), inklusive geplanter Workouts bis dahin."""
    days = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    in_week = lambda d: days[0] <= d <= days[-1]  # noqa: E731
    imported = {(a["date"], a.get("sport")) for a in activities}
    items = [_activity_item(a) for a in activities if in_week(a["date"])]
    missed: dict[str, int] = {}  # Tag → verpasste Workouts
    for w in workouts:
        if not in_week(w["date"]):
            continue
        if w.get("status") == "done":
            if (w["date"], w.get("sport")) not in imported:  # sonst schon als Aktivität gezählt
                items.append(_workout_item(w, settings, done=True))
        elif w["date"] >= today.isoformat():
            items.append(_workout_item(w, settings, done=False))
        else:
            missed[w["date"]] = missed.get(w["date"], 0) + 1

    sports: dict[str, dict] = {}
    for it in items:
        sp = sports.setdefault(it["sport"], {"seconds": 0, "done_seconds": 0, "meters": 0.0, "done_meters": 0.0,
                                             "estimated": False, "sessions": 0, "tss": 0.0, "longest": None})
        sp["seconds"] += it["seconds"]
        sp["meters"] += it["meters"]
        sp["sessions"] += 1
        sp["tss"] += it["tss"]
        sp["estimated"] |= it["estimated"]
        if it["done"]:
            sp["done_seconds"] += it["seconds"]
            sp["done_meters"] += it["meters"]
        if not sp["longest"] or it["seconds"] > sp["longest"]["seconds"]:
            sp["longest"] = {"name": it["name"], "date": it["date"], "seconds": it["seconds"], "meters": round(it["meters"])}

    intensity = {"easy": 0, "moderate": 0, "hard": 0}
    for it in items:
        if it["sport"] in ENDURANCE_SPORTS and it["intensity"]:
            for k, v in it["intensity"].items():
                intensity[k] += v

    day_list = []
    for d in days:
        today_items = [it for it in items if it["date"] == d]
        by_sport: dict[str, int] = {}
        for it in today_items:
            by_sport[it["sport"]] = by_sport.get(it["sport"], 0) + it["seconds"]
        day_list.append({"date": d, "seconds": sum(it["seconds"] for it in today_items),
                         "tss": round(sum(it["tss"] for it in today_items)), "sessions": len(today_items),
                         "missed": missed.get(d, 0),
                         "done": bool(today_items) and all(it["done"] for it in today_items), "by_sport": by_sport})

    endurance = [it for it in items if it["sport"] in ENDURANCE_SPORTS]
    info = periodization.week_info(settings, monday)
    return {
        "week_start": days[0], "week_end": days[-1],
        "week": {k: info.get(k) for k in ("block_name", "recovery", "cycle_week", "cycle_len", "cycle_no", "race_week",
                                          "heat", "heat_sessions", "target_hours", "weeks_to_race")},
        "days": day_list,
        "sports": {k: {**v, "tss": round(v["tss"]), "meters": round(v["meters"]), "done_meters": round(v["done_meters"])}
                   for k, v in sports.items()},
        "totals": {
            "seconds": sum(it["seconds"] for it in items), "done_seconds": sum(it["seconds"] for it in items if it["done"]),
            "endurance_seconds": sum(it["seconds"] for it in endurance),
            "endurance_done_seconds": sum(it["seconds"] for it in endurance if it["done"]),
            "tss": round(sum(it["tss"] for it in items)), "done_tss": round(sum(it["tss"] for it in items if it["done"])),
            "sessions": len(items), "done_sessions": sum(it["done"] for it in items), "missed": sum(missed.values()),
            "rest_days": sum(1 for d in day_list if not d["sessions"] and not d["missed"]),
        },
        "intensity": intensity,
        "hard_sessions": [{k: it[k] for k in ("date", "sport", "name", "done")}
                          for it in sorted(items, key=lambda x: x["date"]) if it["hard"] and it["sport"] in ENDURANCE_SPORTS],
        "load": _load_end(load),
    }
