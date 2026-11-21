"""Belastungsmodell (Banister / Performance Management Chart).

CTL = Fitness (42-Tage-Durchschnitt der täglichen TSS)
ATL = Ermüdung (7-Tage-Durchschnitt)
TSB = Form = CTL − ATL des Vortags
"""
from datetime import date, timedelta

CTL_DAYS = 42
ATL_DAYS = 7


def daily_tss(activities: list[dict], workouts: list[dict]) -> dict[str, float]:
    """TSS pro Tag aus importierten Aktivitäten plus manuell als erledigt markierten Workouts."""
    days: dict[str, float] = {}
    for a in activities:
        days[a["date"]] = days.get(a["date"], 0.0) + float(a.get("tss") or 0)
    for w in workouts:
        if w.get("status") == "done" and w.get("actual_tss") is not None:
            days[w["date"]] = days.get(w["date"], 0.0) + float(w["actual_tss"])
    return days


def step_load(ctl: float, atl: float, tss: float) -> tuple[float, float]:
    return ctl + (tss - ctl) / CTL_DAYS, atl + (tss - atl) / ATL_DAYS


def compute_series(tss_by_day: dict[str, float], start: date, end: date) -> list[dict]:
    """Tagesreihe von start bis end. Vor `start` liegende Tage werden zum Einschwingen genutzt."""
    first = min([date.fromisoformat(d) for d in tss_by_day] + [start])
    ctl = atl = 0.0
    series = []
    day = first
    while day <= end:
        tsb = ctl - atl
        tss = tss_by_day.get(day.isoformat(), 0.0)
        ctl, atl = step_load(ctl, atl, tss)
        if day >= start:
            series.append({"date": day.isoformat(), "tss": round(tss, 1), "ctl": round(ctl, 1),
                           "atl": round(atl, 1), "tsb": round(tsb, 1)})
        day += timedelta(days=1)
    return series


def form_label(tsb: float) -> str:
    if tsb > 25:
        return "Sehr frisch – Fitness geht zurück"
    if tsb > 5:
        return "Frisch – gut für Wettkämpfe"
    if tsb > -10:
        return "Neutral"
    if tsb > -30:
        return "Produktives Training"
    return "Überlastungsrisiko"
