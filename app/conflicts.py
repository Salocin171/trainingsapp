"""Konflikte zwischen geplanten Workouts und Wettkämpfen erkennen – mit Änderungsvorschlag.

Geplante Workouts werden nie automatisch geändert. Diese Prüfung zeigt, was nicht zu den Regeln aus
races.py passt, und schlägt eine konkrete Änderung vor, die der Nutzer übernehmen kann.

Regeln (nur zukünftige, noch nicht erledigte Workouts):
- Renntag: weiteres Workout am Wettkampftag → entfernen
- Taper (B/A): harte Einheit in den letzten 3 Tagen → locker; Vortag → kurze Aktivierung;
  zu lang (Vortag > 40 min, 2–3 Tage vorher > 60 min, früher > 90 min) → kürzen; Stabi → entfernen
- Taper (C): harte Einheit → locker
- Nach dem Rennen: Regenerationstage → nichts Hartes, nicht über 50 min, kein Stabi; Erholung → keine Intensität;
  Laufpause → Rad statt Laufen (oder entfernen, wenn am Tag schon Rad geplant ist)
"""
from datetime import date

from . import races, templates
from .workouts import total_duration

TAPER_MAX_MINUTES = {1: 40, 2: 60, 3: 60}   # Tage vor dem B-/A-Wettkampf → maximale Dauer
TAPER_MAX_DEFAULT = 90
REST_MAX_MINUTES = 40   # Vorschlag für Regenerationstage
REST_TOLERANCE = 50     # erst ab dieser Dauer melden (kleine Abweichungen sind kein Problem)


def _minutes(w: dict) -> int:
    return round(total_duration(w.get("steps", [])) / 60)


def _replacement(w: dict, kind: str, sport: str, minutes: int, race: dict) -> dict:
    """Neues Workout am selben Tag, Sync-Infos bleiben erhalten (Geräte werden aktualisiert)."""
    new = templates.build(kind, sport, minutes)
    return {
        **w, **new, "date": w["date"],
        "name": f"{new['name']} (statt {w.get('name', 'Workout')})"[:120],
        "description": f"Angepasst wegen {race['name']} am {race['date']}. {new['description']}",
    }


def race_list(settings: dict, b_c_races: list[dict]) -> list[dict]:
    """A-Rennen aus den Einstellungen plus B/C-Wettkämpfe."""
    a = [{"name": settings.get("goal_name") or "Wettkampf", "date": settings["goal_date"], "priority": "A",
          "race_type": settings.get("race_type") or "other"}] if settings.get("goal_date") else []
    return a + list(b_c_races)


def check(workouts: list[dict], race_list_: list[dict], today: date) -> list[dict]:
    """→ [{workout_id, date, sport, name, race, phase, problem, action: update|delete, proposal}]"""
    out = []
    by_day = {}
    for w in workouts:
        by_day.setdefault(w["date"], []).append(w)
    for w in workouts:
        if w.get("status") == "done" or w["date"] < today.isoformat():
            continue
        e = races.effect(date.fromisoformat(w["date"]), race_list_)
        if not e:
            continue
        r, days, sport, minutes = e["race"], e["days"], w.get("sport"), _minutes(w)
        prio = r.get("priority", "C")
        found = None  # (Phase, Problem, Aktion, Vorschlag)

        if e["type"] == "race":
            found = ("Renntag", "Am Wettkampftag ist zusätzlich ein Workout geplant.", "delete", None)
        elif e["type"] == "before":
            limit = TAPER_MAX_MINUTES.get(days, TAPER_MAX_DEFAULT)
            if sport == "strength" and prio != "C":
                found = ("Taper", "Stabi/Kraft im Mini-Taper erzeugt Muskelkater.", "delete", None)
            elif sport in templates.ENDURANCE_SPORTS and prio != "C" and days == 1 and (templates.is_hard_workout(w) or minutes > limit):
                found = ("Taper", "Am Vortag nur kurz aktivieren.", "update",
                         _replacement(w, "openers", sport, 30 if sport == "ride" else 20, r))
            elif sport in templates.ENDURANCE_SPORTS and templates.is_hard_workout(w) and (prio == "C" or days <= 3):
                found = ("Taper", f"Harte Einheit {days} Tag(e) vor dem Wettkampf.", "update",
                         _replacement(w, "endurance", sport, min(minutes, limit), r))
            elif sport in templates.ENDURANCE_SPORTS and prio != "C" and minutes > limit:
                found = ("Taper", f"{minutes} min sind im Mini-Taper zu lang (max. {limit} min).", "update",
                         _replacement(w, "recovery" if days <= 3 else "endurance", sport, limit, r))
        else:  # nach dem Rennen
            same_day_ride = any(x.get("sport") == "ride" and x is not w for x in by_day.get(w["date"], []))
            if sport == "run" and days <= e["no_run"]:
                found = ("Laufpause", f"Laufpause nach dem Wettkampf (Tag {days}/{e['no_run']}).",
                         *(("delete", None) if same_day_ride else
                           ("update", _replacement(w, "recovery", "ride", min(max(minutes, 30), 60), r))))
            elif days <= e["rest"]:
                if sport == "strength":
                    found = ("Regeneration", "Kein Stabi in den ersten Tagen nach dem Wettkampf.", "delete", None)
                elif sport in templates.ENDURANCE_SPORTS and (templates.is_hard_workout(w) or minutes > REST_TOLERANCE):
                    found = ("Regeneration", f"Tag {days} nach dem Wettkampf: nur kurz und sehr locker.", "update",
                             _replacement(w, "recovery", sport, min(minutes, REST_MAX_MINUTES), r))
            elif days <= e["recovery"] and sport in templates.ENDURANCE_SPORTS and templates.is_hard_workout(w):
                found = ("Erholung", f"Intensität in der Erholung (Tag {days}/{e['recovery']}).", "update",
                         _replacement(w, "endurance", sport, round(minutes * 0.8), r))

        if found:
            phase, problem, action, proposal = found
            out.append({
                "workout_id": w["id"], "date": w["date"], "sport": sport, "name": w.get("name"), "minutes": minutes,
                "race": {"name": r["name"], "date": r["date"], "priority": prio}, "phase": phase,
                "problem": problem, "action": action, "proposal": proposal,
            })
    return out
