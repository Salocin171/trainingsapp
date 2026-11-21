"""Umfang: Wochenstunden (Soll / erledigt / geplant) und eigene Ziele in Stunden oder Kilometern.

Wochenstunden = Schwimmen + Rad + Laufen. Stabi, Dehnen usw. werden getrennt als "extra" gezählt.

Erledigt = importierte Aktivitäten plus als erledigt markierte Workouts, für die es am selben Tag
keine importierte Aktivität derselben Sportart gibt (sonst würde doppelt gezählt).
Kilometer gibt es nur aus importierten Aktivitäten, geplante Workouts sind zeitbasiert.
"""
from calendar import monthrange
from datetime import date, timedelta

from . import periodization
from .templates import ENDURANCE_SPORTS
from .workouts import total_duration

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
