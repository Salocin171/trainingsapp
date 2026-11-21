"""Subjektives Feedback (RPE 0–10, Befinden 1–5) auswerten.

Quellen: Feedback zu importierten Aktivitäten (Tabelle feedback) und zu Workouts (Felder rpe/feel).
Regeln (Schwellen hier anpassen):
1. Lockere Einheit mit RPE ≥ 8 in den letzten 2 Tagen → Warnung, heute/morgen nichts Hartes.
2. Ø-RPE der letzten 3 Einheiten (5 Tage) ≥ 7 und (TSB < −20 oder 2× Befinden ≤ 2) → 2 Tage reduzieren.
3. Mindestens 2 harte Einheiten mit RPE ≤ 3 in 21 Tagen → Schwellen vermutlich zu niedrig, Test einplanen.
"""
from datetime import date, timedelta

from . import templates
from .workouts import intensity_factor

EASY_RPE_ALARM = 8
FATIGUE_RPE = 7
TOO_EASY_RPE = 3


def _activity_intensity(a: dict) -> tuple[bool, bool]:
    """(locker?, hart?) aus IF oder Pulszonen der Aktivität."""
    m = a.get("metrics") or {}
    if m.get("if"):
        return m["if"] < 0.75, m["if"] >= 0.88
    zones = m.get("hr_zones")
    if zones and sum(zones):
        share_low = (zones[0] + zones[1]) / sum(zones)
        share_high = (zones[3] + zones[4]) / sum(zones)
        return share_low >= 0.8, share_high >= 0.25
    return False, False


def entries(workouts: list[dict], activities: list[dict]) -> list[dict]:
    """Alle Feedback-Einträge als {date, sport, rpe, feel, easy, hard, label}, nach Datum sortiert."""
    out = []
    for a in activities:
        fb = a.get("feedback") or {}
        if fb.get("rpe") is not None or fb.get("feel") is not None:
            easy, hard = _activity_intensity(a)
            out.append({"date": a["date"], "sport": a["sport"], "rpe": fb.get("rpe"), "feel": fb.get("feel"),
                        "easy": easy, "hard": hard, "label": a["name"]})
    for w in workouts:
        if w.get("rpe") is not None or w.get("feel") is not None:
            hard = templates.is_hard(w.get("template", "")) or intensity_factor(w) >= 0.85
            out.append({"date": w["date"], "sport": w.get("sport"), "rpe": w.get("rpe"), "feel": w.get("feel"),
                        "easy": not hard and intensity_factor(w) < 0.75, "hard": hard, "label": w.get("name", "")})
    return sorted(out, key=lambda e: e["date"])


def evaluate(items: list[dict], tsb: float, today: date) -> dict:
    """→ {"warnings", "hints", "easy_until": Datum bis einschl. dem nichts Hartes vorgeschlagen wird | None,
          "reduce_until": Datum bis einschl. dem Umfang −20 % | None, "reason": Begründung für Vorschläge}"""
    out = {"warnings": [], "hints": [], "easy_until": None, "reduce_until": None, "reason": ""}
    iso = lambda d: d.isoformat()  # noqa: E731
    recent = [e for e in items if iso(today - timedelta(days=1)) <= e["date"] <= iso(today)]

    alarm = [e for e in recent if e["easy"] and (e["rpe"] or 0) >= EASY_RPE_ALARM]
    if alarm:
        e = alarm[-1]
        out["warnings"].append(f"Lockere Einheit „{e['label']}“ fühlte sich sehr hart an (RPE {e['rpe']:g}). "
                               "Möglicherweise ermüdet oder krank – heute und morgen nichts Hartes.")
        out["easy_until"] = iso(today + timedelta(days=1))
        out["reason"] = f"Lockere Einheit mit RPE {e['rpe']:g} – Erholung zuerst"

    last = [e for e in items if e["date"] >= iso(today - timedelta(days=5)) and e["rpe"] is not None][-3:]
    low_feel = [e for e in items if e["date"] >= iso(today - timedelta(days=2)) and (e["feel"] or 5) <= 2]
    if len(last) == 3:
        avg = sum(e["rpe"] for e in last) / 3
        if avg >= FATIGUE_RPE and (tsb < -20 or len(low_feel) >= 2):
            out["warnings"].append(f"Hohe Anstrengung zuletzt (Ø RPE {avg:.1f})"
                                   + (f" bei TSB {tsb:.0f}" if tsb < -20 else " und schlechtes Befinden")
                                   + " – die nächsten 2 Tage reduziert.")
            out["easy_until"] = max(out["easy_until"] or "", iso(today + timedelta(days=1)))
            out["reduce_until"] = iso(today + timedelta(days=1))
            out["reason"] = out["reason"] or f"Ø RPE {avg:.1f} zuletzt – Belastung reduziert"

    too_easy = [e for e in items if e["date"] >= iso(today - timedelta(days=21)) and e["hard"]
                and e["rpe"] is not None and e["rpe"] <= TOO_EASY_RPE]
    if len(too_easy) >= 2:
        sports = sorted({e["sport"] for e in too_easy})
        out["hints"].append(f"{len(too_easy)} harte Einheiten fühlten sich leicht an (RPE ≤ {TOO_EASY_RPE}, "
                            f"{', '.join(sports)}). Schwellen sind vermutlich zu niedrig – Test einplanen.")
    return out
