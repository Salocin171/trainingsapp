"""Periodisierung: Trainingsblöcke, Belastungs-/Entlastungswochen, Wochenstunden, Hitzetraining.

Alles wird rückwärts vom Wettkampf gezählt. `weeks_out` = Anzahl Wochen (Mo–So) bis zur
Rennwoche, die Rennwoche selbst hat weeks_out = 0.

    … Grundlage | Aufbau 1 | Aufbau 2 | Wettkampfspezifisch | Tapering | Rennen | Regeneration

Der Belastungsrhythmus (z. B. 3 Wochen Belastung, 1 Woche Entlastung) ist ebenfalls am
Wettkampf ausgerichtet: Die letzte Woche vor dem Tapering ist immer die härteste Woche.
Alternativ legt die Einstellung `cycle_start` (Montag der 1. Belastungswoche) den Rhythmus fest –
dann wird ab diesem Datum vorwärts gezählt, z. B. passend zu einem eigenen Saisonplan. Fiele die Entlastung
direkt vor das Tapering, bleibt diese Woche eine Belastungswoche.
`taper_weeks` überschreibt die Taper-Länge der Wettkampfart (inkl. Rennwoche).
Anpassen: Blocklängen in RACE_PLANS, Umfang in BLOCK_VOLUME, Hitzetraining in HEAT_SESSIONS.
"""
from datetime import date, timedelta

# Blöcke rückwärts vom Wettkampf: (Schlüssel, Länge in Wochen); None = alles davor
RACE_PLANS = {
    "ironman": [("taper", 3), ("peak", 8), ("build2", 8), ("build1", 8), ("base", None)],
    "half": [("taper", 2), ("peak", 6), ("build2", 6), ("build1", 6), ("base", None)],
    "other": [("taper", 2), ("peak", 4), ("build2", 5), ("build1", 5), ("base", None)],
}
RACE_TYPES = {"ironman": "Ironman (Langdistanz)", "half": "Ironman 70.3 (Mitteldistanz)", "other": "Anderer Wettkampf"}
BLOCK_NAMES = {
    "base": "Grundlage", "build1": "Aufbau 1", "build2": "Aufbau 2", "peak": "Wettkampfspezifisch",
    "taper": "Tapering", "transition": "Regeneration",
}
BLOCK_FOCUS = {
    "base": "Aerobe Grundlage, Technik, Kraft/Stabi aufbauen",
    "build1": "Schwelle und Sweet Spot, Umfang steigt",
    "build2": "Längere Schwellenblöcke, Koppeltraining, Umfang steigt weiter",
    "peak": "Wettkampftempo, lange Koppeleinheiten, Verpflegung üben",
    "taper": "Umfang runter, Intensität halten, frisch werden",
    "transition": "Erholen nach dem Wettkampf, nur locker und nach Gefühl",
}
# Anteil der Wochenstunden (Einstellung "week_hours") je Block
BLOCK_VOLUME = {"base": 0.8, "build1": 0.9, "build2": 1.0, "peak": 1.05, "transition": 0.4}
TAPER_VOLUME = [0.4, 0.6, 0.75]  # Rennwoche, 1 Woche vorher, 2 Wochen vorher
RECOVERY_VOLUME = 0.6            # Entlastungswoche relativ zur Belastung im Block
TRANSITION_WEEKS = 2             # Regenerationswochen nach dem Wettkampf
# Hitzeakklimatisierung ~6 Wochen vor dem Renntag: weeks_out → Anzahl Hitzeeinheiten in dieser Woche.
# (weeks_out 5 = Woche, die 6 Wochen vor dem Renntag beginnt; Rennwoche selbst ohne neue Reize)
HEAT_SESSIONS = {5: 3, 4: 3, 3: 4, 2: 4, 1: 2}


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def race_date(settings: dict) -> date | None:
    return date.fromisoformat(settings["goal_date"]) if settings.get("goal_date") else None


def _plan(settings: dict) -> list[tuple[str, int | None]]:
    plan = RACE_PLANS.get(settings.get("race_type") or "other", RACE_PLANS["other"])
    taper = int(settings.get("taper_weeks") or 0)
    return [("taper", taper), *plan[1:]] if taper else plan


def _cycle(settings: dict, week_start: date, weeks_out: int | None, taper_len: int, n: int) -> tuple[int, bool] | None:
    """(Woche im Zyklus 1…n, Entlastung?) oder None (kein Rhythmus, z. B. vor dem Zyklusstart)."""
    if not n:
        return None
    if settings.get("cycle_start"):  # fester Start: vorwärts zählen, Woche n ist Entlastung
        k = (week_start - monday(date.fromisoformat(settings["cycle_start"]))).days // 7
        # die letzte Woche vor dem Tapering bleibt Belastung: frisch wird man im Taper, nicht schon davor
        return (k % n + 1, k % n == n - 1 and weeks_out != taper_len) if k >= 0 else None
    if weeks_out is not None:  # rückwärts vom Rennen: letzte Woche vor dem Tapering = letzte Belastungswoche
        pos = (weeks_out - taper_len + 1) % n
        return (n if pos == 0 else n - pos, pos == 0)
    pos = week_start.isocalendar().week % n
    return (n if pos == 0 else pos, pos == 0)


def _block_at(plan: list, weeks_out: int) -> tuple[str, int, int | None]:
    """(Block, erste weeks_out des Blocks, Länge) für eine Woche vor dem Rennen."""
    start = 0
    for key, length in plan:
        if length is None or weeks_out < start + length:
            return key, start, length
        start += length
    raise AssertionError("Plan muss mit einem offenen Block enden")


def _load_step(cycle_week: int, cycle_len: int) -> float:
    """Belastungswochen steigern sich innerhalb des Zyklus, z. B. 0.9 → 1.0 → 1.1."""
    load_weeks = max(1, cycle_len - 1)
    return 0.9 + 0.2 * (cycle_week - 1) / max(1, load_weeks - 1)


def week_info(settings: dict, day: date) -> dict:
    """Alles über die Trainingswoche, in der `day` liegt."""
    start = monday(day)
    n = int(settings.get("recovery_every") or 0)
    hours = float(settings.get("week_hours") or 0)
    race = race_date(settings)
    info = {
        "week_start": start.isoformat(), "block": "base", "block_week": None, "block_weeks": None,
        "cycle_week": None, "cycle_len": n or None, "recovery": False, "weeks_to_race": None,
        "heat": False, "heat_sessions": 0, "race_week": False,
    }
    volume = BLOCK_VOLUME["base"]

    weeks_out = (monday(race) - start).days // 7 if race else None
    if weeks_out is not None and weeks_out >= 0:
        plan = _plan(settings)
        block, first, length = _block_at(plan, weeks_out)
        taper_len = plan[0][1]
        info.update(block=block, weeks_to_race=weeks_out, race_week=weeks_out == 0)
        if length:
            info.update(block_week=first + length - weeks_out, block_weeks=length)
        if block == "taper":
            volume = TAPER_VOLUME[min(weeks_out, len(TAPER_VOLUME) - 1)]
        else:
            volume = BLOCK_VOLUME[block]
            cycle = _cycle(settings, start, weeks_out, taper_len, n)
            if cycle:
                info.update(cycle_week=cycle[0], recovery=cycle[1])
        if weeks_out in HEAT_SESSIONS:
            info.update(heat=True, heat_sessions=HEAT_SESSIONS[weeks_out])
    elif weeks_out is not None and -weeks_out <= TRANSITION_WEEKS:
        info["block"] = "transition"
        volume = BLOCK_VOLUME["transition"]
    elif cycle := _cycle(settings, start, None, 0, n):
        info.update(cycle_week=cycle[0], recovery=cycle[1])
    if settings.get("cycle_start") and start < monday(date.fromisoformat(settings["cycle_start"])):
        info["cycle_starts"] = settings["cycle_start"]  # Vorlauf vor dem 1. Zyklus (z. B. Reset-Block)

    if info["cycle_week"]:
        volume *= RECOVERY_VOLUME if info["recovery"] else _load_step(info["cycle_week"], n)
    info["block_name"] = BLOCK_NAMES[info["block"]]
    info["focus"] = BLOCK_FOCUS[info["block"]]
    info["target_hours"] = round(hours * volume, 1)
    return info


def next_recovery_week(settings: dict, day: date) -> str | None:
    """Montag der nächsten Entlastungswoche (oder None, z. B. im Tapering)."""
    for i in range(1, 13):
        info = week_info(settings, monday(day) + timedelta(weeks=i))
        if info["block"] == "taper":
            return None
        if info["recovery"]:
            return info["week_start"]
    return None


def timeline(settings: dict, today: date) -> list[dict]:
    """Blöcke von heute bis zum Rennen mit Start/Ende (für die Übersicht)."""
    race = race_date(settings)
    if not race or race < today:
        return []
    race_monday = monday(race)
    blocks, offset = [], 0
    for key, length in _plan(settings):
        last = race_monday - timedelta(weeks=offset)          # Montag der letzten Blockwoche
        first = race_monday - timedelta(weeks=offset + length - 1) if length else monday(today)
        end = race if offset == 0 else last + timedelta(days=6)
        if end >= today:
            blocks.append({"key": key, "name": BLOCK_NAMES[key], "start": max(first, monday(today)).isoformat(),
                           "end": end.isoformat()})
        if length is None:
            break
        offset += length
    return list(reversed(blocks))


# --- Ziel-CTL und Rampenrisiko ----------------------------------------------
# Anteil, um den sich die CTL pro Woche auf den Tagesdurchschnitt der TSS zubewegt (42-Tage-Konstante)
CTL_WEEK_FACTOR = 1 - (1 - 1 / 42) ** 7
TSS_PER_HOUR = 56  # ≈ IF 0,75 – typischer Wochenschnitt im Ausdauertraining
# CTL-Anstieg pro Woche: (CTL bis, niedriges Risiko bis, mittleres Risiko bis) – darüber hohes Risiko
# Quelle: TrainingPeaks-Blog „Track triathlon training“
RAMP_RISK = [(45, 3, 6), (70, 4, 7), (float("inf"), 5, 8)]


def ramp_risk(ctl: float, ramp: float) -> str:
    """'low' | 'medium' | 'high' für einen CTL-Anstieg pro Woche bei aktueller CTL."""
    for ctl_max, low, medium in RAMP_RISK:
        if ctl <= ctl_max:
            return "low" if ramp <= low else "medium" if ramp <= medium else "high"
    return "high"


def ctl_plan(settings: dict, today: date, ctl: float) -> dict | None:
    """Was braucht es, um die Ziel-CTL bis zum Beginn des Taperings zu erreichen?"""
    target, race = float(settings.get("target_ctl") or 0), race_date(settings)
    if not target or not race or race < today:
        return None
    taper_weeks = _plan(settings)[0][1]
    taper_start = monday(race) - timedelta(weeks=taper_weeks - 1)
    weeks = (taper_start - today).days / 7
    if weeks < 1:
        return {"target": target, "ctl": round(ctl, 1), "taper_start": taper_start.isoformat(), "weeks": 0}
    ramp = (target - ctl) / weeks
    weekly_tss = 7 * (ctl + ramp / CTL_WEEK_FACTOR)  # nötiger Ø-Tages-TSS, damit CTL um `ramp` je Woche steigt
    return {
        "target": target, "ctl": round(ctl, 1), "taper_start": taper_start.isoformat(), "weeks": round(weeks, 1),
        "ramp": round(ramp, 1), "risk": ramp_risk(ctl, ramp),
        "weekly_tss": round(weekly_tss), "weekly_hours": round(weekly_tss / TSS_PER_HOUR, 1),
    }
