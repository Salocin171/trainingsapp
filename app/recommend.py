"""Trainingsempfehlungen.

Ablauf:
1. Woche einordnen (periodization.week_info): Block, Belastungs-/Entlastungswoche, Soll-Stunden,
   Hitzetraining.
2. Wochenmuster abarbeiten: Jeder Tag hat eine Liste von Einheiten (Sport + Typ). Bereits geplante
   Workouts und heute erledigte Aktivitäten füllen passende Einheiten, freie Einheiten bekommen einen
   Vorschlag. Die noch offenen Wochenstunden werden gewichtet auf die freien Einheiten verteilt.
3. Regeln passen jeden Vorschlag an (Ermüdung, Abstand harter Einheiten, Bereitschaft, Rennwoche …),
   die Belastung wird Tag für Tag mitsimuliert.
Jede Anpassung wird als Begründung mitgegeben, damit nachvollziehbar bleibt, warum.
"""
from datetime import date, timedelta

from . import periodization, races as race_rules, templates
from .load import form_label, step_load
from .workouts import estimate_tss, intensity_factor

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
ENDURANCE = templates.ENDURANCE_SPORTS
SPORT_DE = {"swim": "Schwimmen", "ride": "Rad", "run": "Laufen", "strength": "Stabi", "mobility": "Dehnen/Yoga"}
TYPE_DE = {"recovery": "Regeneration", "easy": "locker", "hard": "hart", "long": "lang"}

# Anteil einer Einheit an den Wochenstunden: Typ × Sportart
TYPE_WEIGHT = {"recovery": 0.5, "easy": 1.0, "hard": 1.1, "long": 2.2}
SPORT_WEIGHT = {"swim": 0.7, "ride": 1.3, "run": 0.8}
# Feste Dauer (Minuten) für Stabi/Kraft je Block und für Dehnen/Yoga
STRENGTH_MINUTES = {"base": 45, "build1": 40, "build2": 35, "peak": 30, "taper": 20, "transition": 30}
MOBILITY_MINUTES = 25
HARD_ROTATION = {
    "base": ["sweetspot", "tempo"],
    "build1": ["threshold", "sweetspot"],
    "build2": ["threshold", "vo2max", "sweetspot"],
    "peak": ["race_pace", "threshold"],
    "taper": ["threshold", "race_pace"],  # Umfang sinkt, Intensität bleibt
    "transition": ["endurance"],
}
BRICK_MINUTES = {"build2": 20, "peak": 30, "taper": 15}
POOR_HRV = {"LOW", "POOR", "UNBALANCED"}

HEAT_NOTE = ("\n\nHitzetraining: Indoor ohne Ventilator bzw. mit einer Lage mehr, locker bleiben (Puls zählt, "
             "nicht Watt/Tempo). Mit Elektrolyten trinken, vorher/nachher wiegen. "
             "Alternative: 20–30 min Sauna direkt nach dem Training.")
NUTRITION_NOTE = ("\n\nVerpflegung wie im Rennen üben: 60–90 g Kohlenhydrate pro Stunde, Getränke und Gels "
                  "aus dem Wettkampf testen.")


def slots_for(settings: dict, day: date) -> list[dict]:
    return list(settings["week_pattern"].get(WEEKDAYS[day.weekday()], []))


def _open_slots(slots: list[dict], taken_sports: list[str]) -> list[dict]:
    """Einheiten, die noch nicht durch Geplantes oder Erledigtes belegt sind."""
    taken = list(taken_sports)
    out = []
    for slot in slots:
        if slot["sport"] in taken:
            taken.remove(slot["sport"])
        else:
            out.append(slot)
    return out


def _fixed_minutes(slot: dict, block: str) -> int | None:
    if slot["sport"] == "strength":
        return STRENGTH_MINUTES[block]
    if slot["sport"] == "mobility":
        return MOBILITY_MINUTES
    return None


def _weight(slot: dict) -> float:
    return TYPE_WEIGHT.get(slot["type"], 1.0) * SPORT_WEIGHT.get(slot["sport"], 1.0)


def _activity_if(a: dict) -> float:
    hours = (a.get("duration") or 0) / 3600
    return (a["tss"] / (hours * 100)) ** 0.5 if hours and a.get("tss") else 0.0


def _is_hard_workout(w: dict) -> bool:
    return templates.is_hard(w.get("template", "")) or intensity_factor(w) >= 0.85


def _downgrade(kind: str) -> str:
    return "recovery" if kind in ("endurance", "recovery", "openers") else "endurance"


def analyze(series: list[dict], activities: list[dict], wellness: dict, settings: dict, today: date,
            fb: dict | None = None, races: list[dict] | None = None) -> dict:
    """Zustand, aktueller Block, Warnhinweise. `fb` = Ergebnis von feedback.evaluate()."""
    current = series[-1] if series else {"ctl": 0, "atl": 0, "tsb": 0}
    week_ago = series[-8] if len(series) >= 8 else (series[0] if series else current)
    ramp = round(current["ctl"] - week_ago["ctl"], 1)
    week = periodization.week_info(settings, today)
    race = periodization.race_date(settings)
    days_left = (race - today).days if race and race >= today else None
    warnings, hints = [], []

    if current["tsb"] < -30:
        warnings.append(f"Form sehr negativ (TSB {current['tsb']}). Erholung einplanen, sonst droht Übertraining.")
    risk = periodization.ramp_risk(current["ctl"], ramp)
    if risk == "high":
        warnings.append(f"Fitness steigt sehr schnell (+{ramp} CTL/Woche bei CTL {current['ctl']:.0f}) – "
                        "hohes Risiko für Verletzung, Krankheit oder Überlastung.")
    elif risk == "medium":
        hints.append(f"Rampe +{ramp} CTL/Woche: mittleres Risiko bei CTL {current['ctl']:.0f}.")
    plan = periodization.ctl_plan(settings, today, current["ctl"])
    if plan and plan.get("risk") == "high":
        warnings.append(f"Ziel-CTL {plan['target']:.0f} braucht +{plan['ramp']} CTL/Woche – das ist zu steil. "
                        "Ziel senken oder mehr Zeit einplanen.")
    for r in races or []:
        days = (date.fromisoformat(r["date"]) - today).days
        if 0 <= days <= 14:
            hints.append(f"{r.get('priority', 'C')}-Wettkampf {r['name']} in {days} Tagen"
                         + (" – Mini-Taper 3 Tage vorher, danach Erholung." if r.get("priority") == "B" else
                            " – wird durchtrainiert, nur der Vortag ist locker."))
    last7 = series[-7:]
    if last7 and all(s["tss"] >= 20 for s in last7):
        warnings.append("Kein Ruhetag in den letzten 7 Tagen.")
    if wellness.get("readiness") is not None and wellness["readiness"] < 35:
        warnings.append(f"Garmin-Trainingsbereitschaft niedrig ({wellness['readiness']}). Heute eher locker.")
    if wellness.get("hrv_status") in POOR_HRV:
        warnings.append(f"HRV-Status: {wellness['hrv_status']}. Hinweis auf unvollständige Erholung.")

    recent = [a for a in activities if a["date"] >= (today - timedelta(days=28)).isoformat()
              and a["sport"] in ENDURANCE]
    # 80/20: bevorzugt echte Zeit in Pulszonen (Z1–2 locker, Z3–5 intensiv), sonst grob über die Intensität
    zones = [(a.get("metrics") or {}).get("hr_zones") for a in recent]
    zone_time = [sum(z) for z in zones if z]
    if sum(zone_time) > 3600 * 4:
        total_time = sum(zone_time)
        hard_time = sum(sum(z[2:]) for z in zones if z)
        basis = "Pulszonen"
    else:
        total_time = sum(a["duration"] or 0 for a in recent)
        hard_time = sum(a["duration"] or 0 for a in recent if _activity_if(a) >= 0.85)
        basis = "geschätzt"
    if total_time > 3600 * 4:
        share = round(hard_time / total_time * 100)
        if share > 25:
            warnings.append(f"{share} % der Ausdauerzeit (28 Tage, {basis}) war intensiv (Z3–5). "
                            "Ziel ~20 % intensiv / 80 % locker.")
        else:
            hints.append(f"Intensitätsverteilung ok: {share} % intensiv / {100 - share} % locker (28 Tage, {basis}).")
    if not activities:
        hints.append("Noch keine Aktivitäten importiert – Empfehlungen basieren nur auf Planung.")
    if week["heat"]:
        hints.append(f"Hitzeakklimatisierung: {week['heat_sessions']} Hitzeeinheiten diese Woche "
                     "(locker, Indoor ohne Ventilator oder Sauna nach dem Training).")
    if week["block"] == "peak":
        hints.append("Wettkampfspezifisch: Freiwasser mit Neo schwimmen, Rennrad in Aeroposition, "
                     "Verpflegung und Material wie im Rennen testen.")
    if week["race_week"]:
        hints.append("Rennwoche: Material checken, Rad zum Check-in vorbereiten, ab 2 Tage vorher "
                     "Kohlenhydrate laden (8–10 g pro kg Körpergewicht), viel schlafen.")

    return {
        "ctl": current["ctl"], "atl": current["atl"], "tsb": current["tsb"],
        "form": form_label(current["tsb"]), "ramp": ramp,
        "week_tss": round(sum(s["tss"] for s in last7)),
        "week": week, "next_recovery": periodization.next_recovery_week(settings, today), "ctl_plan": plan,
        "timeline": periodization.timeline(settings, today),
        "days_to_goal": days_left, "goal_name": settings.get("goal_name", ""),
        "wellness": wellness, "warnings": warnings + (fb or {}).get("warnings", []),
        "hints": hints + (fb or {}).get("hints", []),
    }


def _week_budgets(settings: dict, today: date, last_day: date) -> dict:
    """Minuten pro Gewichtseinheit für jede Woche im Planungszeitraum.

    Die Soll-Stunden (nur Schwimmen/Rad/Laufen; Stabi und Dehnen kommen obendrauf) werden nach Gewicht auf
    alle Ausdauereinheiten des Wochenmusters verteilt. Jede Einheit bekommt so ihren fairen Anteil – verpasste Einheiten vom Wochenanfang
    werden bewusst nicht auf die restlichen Tage gepackt.
    """
    budgets = {}
    week = periodization.monday(today)
    while week <= last_day:
        info = periodization.week_info(settings, week)
        weight = sum(_weight(slot) for i in range(7) for slot in slots_for(settings, week + timedelta(days=i))
                     if slot["sport"] in ENDURANCE)
        budgets[week.isoformat()] = {"info": info, "per_weight": info["target_hours"] * 60 / weight if weight else 0.0}
        week += timedelta(weeks=1)
    return budgets


def plan_days(settings: dict, today: date, state: dict, workouts: list[dict], activities: list[dict],
              wellness: dict, horizon: int = 7, fb: dict | None = None,
              races: list[dict] | None = None) -> list[dict]:
    """Vorschläge für freie Einheiten ab heute (mehrere pro Tag möglich).

    `state` = {"ctl", "atl"} am Ende von gestern, optional "today_tss" (heute bereits trainiert).
    `workouts` = Workouts im Planungszeitraum (geplant und erledigt), weitere werden ignoriert.
    """
    ctl, atl = state["ctl"], state["atl"]
    last_day = today + timedelta(days=horizon - 1)
    race = periodization.race_date(settings)
    planned = [w for w in workouts if w.get("status") != "done" and w["date"] >= today.isoformat()]

    taken_by_day: dict[str, list[str]] = {}
    for w in workouts:
        if w["date"] >= today.isoformat():
            taken_by_day.setdefault(w["date"], []).append(w.get("sport"))
    for a in activities:
        if a["date"] == today.isoformat():
            taken_by_day.setdefault(a["date"], []).append(a["sport"])
    budgets = _week_budgets(settings, today, last_day)

    # Harte Einheiten je Sport (erledigt oder geplant) – Abstand gilt in beide Richtungen
    hard_dates: dict[str, set[date]] = {}
    for a in activities:
        if _activity_if(a) >= 0.85:
            hard_dates.setdefault(a["sport"], set()).add(date.fromisoformat(a["date"]))
    hard_planned = {(w["date"], w.get("sport")) for w in planned if _is_hard_workout(w)}
    for d, sport in hard_planned:
        hard_dates.setdefault(sport, set()).add(date.fromisoformat(d))
    rotation: dict[str, int] = {}
    heat_used: dict[str, int] = {}

    suggestions = []
    for offset in range(horizon):
        day = today + timedelta(days=offset)
        iso = day.isoformat()
        tsb = ctl - atl
        week = budgets[periodization.monday(day).isoformat()]
        info, block = week["info"], week["info"]["block"]
        days_left = (race - day).days if race else None
        day_tss = sum(estimate_tss(w) for w in planned if w["date"] == iso)
        if offset == 0:
            day_tss += state.get("today_tss", 0.0)
        base = {"date": iso, "weekday": WEEKDAY_DE[day.weekday()], "tsb": round(tsb, 1)}

        if days_left == 0:
            suggestions.append({**base, "kind": "race",
                                "reasons": [f"Wettkampf: {settings.get('goal_name') or 'Ziel'} – viel Erfolg!"]})
            ctl, atl = step_load(ctl, atl, day_tss)
            continue

        effect = race_rules.effect(day, races or [])  # B/C-Wettkampf: Renntag, Mini-Taper oder Erholung
        if effect and effect["type"] == "race":
            r = effect["race"]
            suggestions.append({**base, "kind": "race", "reasons": [f"{r.get('priority', 'C')}-Wettkampf: {r['name']}"]})
            ctl, atl = step_load(ctl, atl, day_tss)
            continue
        race_name = effect["race"]["name"] if effect else ""

        slots = slots_for(settings, day)
        open_slots = _open_slots(slots, taken_by_day.get(iso, []))
        if days_left == 2:
            suggestions.append({**base, "kind": "rest", "reasons": ["2 Tage vor dem Wettkampf: Ruhetag"]})
        elif not any(s["sport"] != "mobility" for s in slots) and not taken_by_day.get(iso):
            suggestions.append({**base, "kind": "rest", "reasons": ["Ruhetag laut Wochenmuster"]})

        hard_today = {sport for (d, sport) in hard_planned if d == iso}
        race_week_opener_done = False
        for slot in open_slots:
            sport, slot_type = slot["sport"], slot["type"]
            reasons = []
            if effect and effect["type"] == "after" and sport == "run" and effect["days"] <= effect["no_run"]:
                if any(s["sport"] == "ride" for s in slots):
                    continue  # Laufpause, Rad ist an dem Tag ohnehin geplant
                sport, slot_type = "ride", "recovery"
                reasons.append(f"Laufpause nach {race_name} (Tag {effect['days']}/{effect['no_run']}) – Rad statt Laufen")
            minutes = _fixed_minutes(slot, block) if sport == slot["sport"] else None

            if sport == "mobility":
                kind = "mobility"
            elif sport == "strength":
                if days_left is not None and 0 < days_left <= 10:
                    continue  # keine neuen Muskelreize kurz vor dem Rennen
                if effect and (effect["type"] == "before" or effect["days"] <= effect["rest"]):
                    continue  # rund um Wettkämpfe kein Stabi
                kind = "stabi"
            else:
                minutes = week["per_weight"] * _weight(slot)
                if slot_type == "hard":
                    options = HARD_ROTATION[block]
                    counter = rotation.get(sport, day.isocalendar().week)
                    kind = options[counter % len(options)]
                    rotation[sport] = counter + 1
                elif slot_type == "long":
                    kind = "race_pace" if block == "peak" and day.isocalendar().week % 2 == 0 else "long"
                else:
                    kind = "recovery" if slot_type == "recovery" else "endurance"

                # --- Regeln -----------------------------------------------------------
                if days_left is not None and 0 < days_left <= 3:
                    if days_left == 2 or race_week_opener_done:
                        continue
                    kind, minutes = "openers", 30 if sport == "ride" else 20
                    race_week_opener_done = True
                    reasons.append("Kurz vor dem Wettkampf: aktivieren statt ermüden")
                if block == "transition":
                    kind = "recovery" if kind == "recovery" else "endurance"
                    reasons.append("Regeneration nach dem Wettkampf: nur locker")
                if templates.is_hard(kind) and info["recovery"]:
                    kind = "endurance"
                    reasons.append("Entlastungswoche: Intensität raus")
                gap = min((abs((day - d).days) for d in hard_dates.get(sport, ())), default=99)
                if templates.is_hard(kind) and gap < 2:
                    reasons.append(f"Harte {SPORT_DE[sport]}-Einheit am Vortag oder Folgetag")
                    kind = "endurance"
                if templates.is_hard(kind) and sport != "swim" and hard_today - {"swim"}:
                    reasons.append("Heute schon eine harte Einheit")
                    kind = "endurance"
                if templates.is_hard(kind) and tsb < -25:
                    reasons.append(f"Hohe Ermüdung (TSB {tsb:.0f}) – Intensität raus")
                    kind = "endurance"
                if tsb < -35:
                    reasons.append(f"Sehr hohe Ermüdung (TSB {tsb:.0f}) – nur Regeneration")
                    kind, minutes = "recovery", min(minutes, 40)
                if offset == 0 and ((wellness.get("readiness") is not None and wellness["readiness"] < 35)
                                    or wellness.get("hrv_status") in POOR_HRV):
                    reasons.append("Garmin meldet niedrige Bereitschaft / HRV")
                    kind, minutes = _downgrade(kind), minutes * 0.7
                if fb and fb["easy_until"] and iso <= fb["easy_until"] and templates.is_hard(kind):
                    reasons.append(fb["reason"])
                    kind = "endurance"
                if fb and fb["reduce_until"] and iso <= fb["reduce_until"]:
                    minutes *= 0.8
                if effect and effect["type"] == "before":
                    prio, days, taper = effect["race"].get("priority", "C"), effect["days"], effect["taper"]
                    if prio == "B" and days == 1:  # Vortag: nur kurz aktivieren
                        if race_week_opener_done:
                            continue
                        kind, minutes = "openers", 30 if sport == "ride" else 20
                        race_week_opener_done = True
                    else:
                        if templates.is_hard(kind) and (prio == "C" or days <= 3):
                            kind = _downgrade(kind)  # bei langem Taper bleibt früh noch etwas Intensität
                        if prio == "B":  # Umfang sinkt Richtung Renntag: 90 % → 60 %
                            minutes *= 0.6 + 0.3 * (days - 1) / max(1, taper - 1)
                    reasons.append(f"{prio}-Wettkampf {race_name} in {days} Tag(en)"
                                   + (": Mini-Taper" if prio == "B" else ": locker bleiben"))
                if effect and effect["type"] == "after" and effect["days"] <= effect["recovery"]:
                    days, rest, recovery = effect["days"], effect["rest"], effect["recovery"]
                    if days <= rest:
                        kind, minutes = "recovery", min(minutes, 40)
                    else:  # keine Intensität, Umfang steigt von 70 % auf 90 %
                        kind = "endurance" if templates.is_hard(kind) or kind == "race_pace" else kind
                        minutes *= 0.7 + 0.2 * (days - rest) / max(1, recovery - rest)
                    reasons.append(f"Erholung nach {race_name} (Tag {days}/{recovery})")

            workout = templates.build(kind, sport, round(minutes or 0))
            heat = False
            if (info["heat"] and sport in ("ride", "run") and kind in ("endurance", "recovery")
                    and heat_used.get(info["week_start"], 0) < info["heat_sessions"]):
                heat_used[info["week_start"]] = heat_used.get(info["week_start"], 0) + 1
                heat = True
                workout["name"] += " (Hitze)"
                workout["description"] += HEAT_NOTE
                reasons.append(f"Hitzetraining {heat_used[info['week_start']]}/{info['heat_sessions']} "
                               f"({info['weeks_to_race']} Wochen vor dem Rennen)")
            if kind in ("long", "race_pace") and block in ("build2", "peak"):
                workout["description"] += NUTRITION_NOTE
            if not reasons:
                week_label = "Entlastungswoche" if info["recovery"] else (
                    f"Belastungswoche {info['cycle_week']}/{info['cycle_len'] - 1}" if info["cycle_week"] else "")
                reasons.append(" · ".join(x for x in (info["block_name"], week_label,
                                                      f"{SPORT_DE[sport]} {TYPE_DE.get(slot_type, '')}") if x))
            if templates.is_hard(kind):
                hard_today.add(sport)
                hard_dates.setdefault(sport, set()).add(day)
            tss = estimate_tss(workout)
            day_tss += tss
            suggestions.append({**base, "kind": kind, "sport": sport, "heat": heat,
                                "workout": {**workout, "date": iso}, "tss": tss, "reasons": reasons})

            # Koppellauf nach langer Radeinheit, wenn an dem Tag kein Lauf vorgesehen ist
            if (sport == "ride" and kind in ("long", "race_pace") and block in BRICK_MINUTES
                    and not any(s["sport"] == "run" for s in slots) and "run" not in taken_by_day.get(iso, [])):
                brick = {**templates.build("brick", "run", BRICK_MINUTES[block]), "date": iso}
                brick_tss = estimate_tss(brick)
                day_tss += brick_tss
                suggestions.append({**base, "kind": "brick", "sport": "run", "heat": False, "workout": brick,
                                    "tss": brick_tss, "reasons": ["Koppeltraining: direkt nach dem Rad laufen"]})

        ctl, atl = step_load(ctl, atl, day_tss)
    return suggestions
