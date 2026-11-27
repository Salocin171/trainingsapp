"""Compliance: geplant vs. erledigt, Farben wie bei TrainingPeaks (Athlete User Guide).

    grün   80–120 % des Plans
    gelb   50–79 % oder 121–150 %
    orange < 50 % oder > 150 %, oder anderes Training als geplant
    rot    verpasst (Tag vorbei, nichts erledigt)
    grau   ungeplante Aktivität

Am selben Tag und in derselben Sportart wird jede Aktivität einem Workout zugeordnet. Sie gilt grob als dasselbe
Training, wenn der Name passt oder die Dauer ungefähr stimmt und die Härte grob passt (hartes Workout: harte Belastung
erkennbar, lockeres Workout: nicht überwiegend hart). Sonst heißt es „anders als geplant“: 30 min locker sind keine 5×1000 m. Von Hand lässt sich das je Aktivität
festlegen (`plan_link` im Feedback: Workout-ID, 0 = gehört zu keinem Plan).

Prozent und Farbe kommen aus der Dauer: Plan-TSS (aus Tempo/Watt) und Garmin-TSS sind beim Laufen nicht vergleichbar.
Nur von Hand erledigte Workouts ohne Aktivität werden über ihren Ist-TSS bewertet.
"""
import re
from datetime import date

from .workouts import FLAT_TSS_PER_HOUR, estimate_tss, flatten, total_duration

# Erlaubte Abweichung der Dauer (Ist / Plan), danach ist es nicht mehr dasselbe Training
DURATION_RANGE = {"swim": (0.5, 2.0), "strength": (0.4, 2.0), "mobility": (0.4, 2.0)}
DEFAULT_DURATION_RANGE = (0.6, 1.6)
HARD_PCT = 88            # ab hier zählt ein Schritt als hart (% von FTP / Schwelle / CSS)
SHORT_REP_SECONDS = 120  # bei kürzeren Wiederholungen reagiert der Puls kaum, also großzügiger prüfen
MUCH_HARDER_SHARE = 0.15  # lockerer Plan, aber so viel der Zeit in Pulszone 4–5: war ein anderes Training
LTHR_KEY = {"run": "lthr_run", "ride": "lthr_ride"}  # Schwellenpuls je Sport (beim Schwimmen zu ungenau)
# Allgemeine Wörter sagen nichts darüber, ob es dasselbe Training ist
NAME_NOISE = {"laufen", "lauf", "radfahren", "rad", "schwimmen", "schwimmbad", "indoor", "locker", "min", "training"}


def color(pct: float) -> str:
    if 80 <= pct <= 120:
        return "green"
    if 50 <= pct <= 150:
        return "yellow"
    return "orange"


def _name_tokens(name: str | None) -> set[str]:
    return {t for t in re.findall(r"\w+", (name or "").lower()) if len(t) > 2 and not t.isdigit() and t not in NAME_NOISE}


def _name_matches(workout: dict, activity: dict) -> bool:
    plan = _name_tokens(workout.get("name"))
    shared = plan & _name_tokens(activity.get("name"))
    return len(shared) >= 2 or (bool(shared) and len(shared) * 2 >= len(plan))


def _duration_problem(workout: dict, seconds: float) -> str | None:
    planned = total_duration(workout.get("steps", []))
    if not planned:
        return None
    low, high = DURATION_RANGE.get(workout.get("sport"), DEFAULT_DURATION_RANGE)
    if low <= seconds / planned <= high:
        return None
    return f"{round(seconds / 60)} statt {round(planned / 60)} min"


def _hard_steps(workout: dict) -> list[dict]:
    return [s for s in flatten(workout.get("steps", []))
            if s["kind"] not in ("warmup", "recovery", "cooldown") and (s["low"] + s["high"]) / 2 >= HARD_PCT]


def _looks_hard(hard: list[dict], activity: dict, settings: dict) -> bool:
    """Passt die Aktivität zu den harten Schritten? Ohne Pulszonen und Leistung lässt sich das nicht widerlegen."""
    m = activity.get("metrics") or {}
    zones, mmp = m.get("hr_zones"), m.get("mmp")
    if not zones and not mmp:
        return True
    longest = max(s["duration"] for s in hard)
    if mmp and settings.get("ftp"):
        durations = [int(d) for d in mmp if int(d) <= longest]
        target = max((s["low"] + s["high"]) / 2 for s in hard) / 100 * settings["ftp"]
        if durations and mmp[str(max(durations))] >= 0.9 * target:
            return True
    short = longest < SHORT_REP_SECONDS
    lthr = settings.get(LTHR_KEY.get(activity.get("sport"), ""))
    if short and lthr and (m.get("max_hr") or 0) >= 0.9 * lthr:
        return True
    if not zones:
        return False
    above_easy = sum(zones[2:])
    return above_easy >= (60 if short else max(180, 0.25 * sum(s["duration"] for s in hard)))


def _difference(workout: dict, activity: dict, settings: dict) -> str | None:
    """Warum die Aktivität nicht dieses Workout war – None, wenn es grob passt."""
    if _name_matches(workout, activity):
        return None
    problem = _duration_problem(workout, activity.get("duration") or 0)
    if problem:
        return problem
    hard = _hard_steps(workout)
    if hard and not _looks_hard(hard, activity, settings):
        return "keine harte Belastung erkennbar"
    zones = (activity.get("metrics") or {}).get("hr_zones") or []
    if not hard and workout.get("sport") in ("run", "ride") and sum(zones[3:]) >= MUCH_HARDER_SHARE * sum(zones or [1]):
        return "deutlich härter als geplant"  # beim Schwimmen ist der Puls dafür zu ungenau
    return None


def _pair_sport_day(planned: list[dict], actual: list[dict], settings: dict) -> dict[int, dict]:
    """Ein Tag, eine Sportart → {Workout-ID: {"activities", "reason"}}, reason gesetzt = anders als geplant."""
    def closeness(w, a):  # Namensgleichheit zuerst, dann die ähnlichste Dauer
        planned_sec = total_duration(w.get("steps", [])) or 1
        return (not _name_matches(w, a), abs((a.get("duration") or 0) / planned_sec - 1))

    pairs: dict[int, dict] = {}
    free = list(actual)
    for w, a in sorted(((w, a) for w in planned for a in actual), key=lambda p: closeness(*p)):
        if w["id"] not in pairs and a in free and _difference(w, a, settings) is None:
            pairs[w["id"]] = {"activities": [a], "reason": None}
            free.remove(a)

    # Unterbrochene Aufzeichnung: weitere Stücke gehören dazu, solange das Workout nicht deutlich überschritten wird
    for w in planned:
        pair = pairs.get(w["id"])
        for a in list(free) if pair else []:
            total = sum(x.get("duration") or 0 for x in pair["activities"]) + (a.get("duration") or 0)
            if total <= 1.25 * total_duration(w.get("steps", [])):
                pair["activities"].append(a)
                free.remove(a)

    for w in planned:
        if w["id"] in pairs or not free:
            continue
        reason = _duration_problem(w, sum(a.get("duration") or 0 for a in free))
        if reason is None and len(free) > 1:  # mehrere Stücke ergeben zusammen das Workout
            pairs[w["id"]] = {"activities": free, "reason": None}
            free = []
            continue
        a = min(free, key=lambda x: closeness(w, x)[1])
        pairs[w["id"]] = {"activities": [a], "reason": _difference(w, a, settings)}
        free.remove(a)
    return pairs


def _pair(workouts: list[dict], activities: list[dict], settings: dict) -> dict[int, dict]:
    pairs: dict[int, dict] = {}
    by_id = {w["id"]: w for w in workouts}
    groups: dict[tuple[str, str], dict] = {}
    for w in workouts:
        groups.setdefault((w["date"], w.get("sport")), {"planned": [], "actual": []})["planned"].append(w)
    for a in activities:
        link = (a.get("feedback") or {}).get("plan_link")
        if link == 0:
            continue
        linked = by_id.get(link)
        if linked and linked["date"] == a["date"]:
            pairs.setdefault(link, {"activities": [], "reason": None})["activities"].append(a)
        elif (a["date"], a["sport"]) in groups:
            groups[(a["date"], a["sport"])]["actual"].append(a)
    for group in groups.values():
        planned = [w for w in group["planned"] if w["id"] not in pairs]
        pairs.update(_pair_sport_day(planned, group["actual"], settings))
    return pairs


def evaluate(workouts: list[dict], activities: list[dict], today: date,
             settings: dict | None = None) -> tuple[dict[int, dict], set[str], dict[str, dict]]:
    """→ ({Workout-ID: {"color", "pct", "basis", "match", "reason"}}, {IDs ungeplanter Aktivitäten},
    {Aktivitäts-ID: {"workout_id", "match"}}). match: "same" | "different"."""
    pairs = _pair(workouts, activities, settings or {})
    result, links = {}, {}
    for w in workouts:
        pair = pairs.get(w["id"])
        planned_sec = total_duration(w.get("steps", []))
        if pair:
            match = "different" if pair["reason"] else "same"
            seconds = sum(a.get("duration") or 0 for a in pair["activities"])
            pct = round(seconds / planned_sec * 100) if planned_sec else 100
            result[w["id"]] = {"color": "orange" if pair["reason"] else color(pct), "pct": pct, "basis": "Dauer",
                               "match": match, "reason": pair["reason"]}
            for a in pair["activities"]:
                links[a["id"]] = {"workout_id": w["id"], "match": match}
        elif w.get("status") == "done":  # von Hand als erledigt markiert, ohne importierte Aktivität
            planned_tss = estimate_tss(w)
            use_tss = w.get("sport") not in FLAT_TSS_PER_HOUR and w.get("actual_tss") is not None and planned_tss > 0
            pct = round(w["actual_tss"] / planned_tss * 100) if use_tss else 100
            result[w["id"]] = {"color": color(pct), "pct": pct, "basis": "TSS" if use_tss else "Dauer"}
        elif w["date"] < today.isoformat():
            result[w["id"]] = {"color": "red", "pct": 0, "basis": ""}
    return result, {a["id"] for a in activities if a["id"] not in links}, links


def mark_matched(workouts: list[dict], activities: list[dict], today: date, settings: dict) -> list[dict]:
    """Workouts, die per Aktivität erledigt sind, gelten als erledigt (sonst zählen sie zusätzlich als noch geplant)."""
    rating = evaluate(workouts, activities, today, settings)[0]
    return [{**w, "status": "done"} if rating.get(w["id"], {}).get("match") == "same" else w for w in workouts]
