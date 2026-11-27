r"""MCP-Server für die Trainingsapp – damit Claude (Claude Code, Claude Desktop) die App bedienen kann.

Dünne Schicht über die HTTP-API der laufenden App (http://127.0.0.1:<PORT>), keine eigene Logik.
Die App muss laufen (Trainingsapp.command bzw. Trainingsapp.bat, Autostart oder F5 in VS Code).

Einmalig registrieren (für alle Claude-Code-Sitzungen), im Ordner der App ausführen:
    claude mcp add trainingsapp --scope user -- "$PWD/.venv/bin/python" "$PWD/app/mcp_server.py"
Windows (PowerShell):
    claude mcp add trainingsapp --scope user -- "$PWD\.venv\Scripts\python.exe" "$PWD\app\mcp_server.py"
"""
import sys
from datetime import date as Date
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ""):  # als Skript gestartet → Projektordner importierbar machen
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app import config, plan_import

BASE = f"http://127.0.0.1:{config.PORT}"
logging.getLogger("httpx").setLevel(logging.WARNING)  # keine Zeile pro Anfrage im MCP-Log
READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
DELETE = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

server = MCPServer(
    name="trainingsapp",
    title="Trainingsapp",
    instructions=(
        "Persönliche Triathlon-Trainingsapp (Vorbereitung auf das Saisonziel aus den Einstellungen). Daten: geplante Workouts, importierte "
        "Garmin-Aktivitäten, Belastung (CTL/ATL/TSB), Periodisierung bis zum Wettkampf, Vorschläge mit Begründung. "
        "Sportarten: swim, ride, run, strength (Stabi), mobility (Dehnen/Yoga). Intensitäten in % von FTP (Rad), "
        "Schwellentempo (Laufen) bzw. CSS (Schwimmen). Vor Änderungen am Plan zuerst get_status und get_calendar "
        "lesen. Workouts nur an Geräte senden (send_to), wenn der Nutzer das möchte."
    ),
)


# ToolError-Meldungen sieht Claude im Klartext; andere Exceptions blendet das MCP-SDK aus.
class AppNotRunning(ToolError):
    pass


def _api(method: str, path: str, text: bool = False, **kwargs):
    try:
        r = httpx.request(method, BASE + path, timeout=120, **kwargs)
    except httpx.ConnectError:
        raise AppNotRunning(f"Die Trainingsapp läuft nicht ({BASE}). Bitte {config.START_SCRIPT} starten.") from None
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except ValueError:
            detail = r.text
        raise ToolError(f"{method} {path} → {r.status_code}: {detail}")
    return r.text if text else r.json()


def _minutes(seconds) -> int:
    return round((seconds or 0) / 60)


def _workout_brief(w: dict) -> dict:
    return {
        "id": w["id"], "date": w["date"], "sport": w.get("sport"), "name": w.get("name"),
        "minutes": _minutes(w.get("duration")), "tss": round(w.get("tss") or 0), "status": w.get("status"),
        "compliance": w.get("compliance"), "synced_to": sorted((w.get("sync") or {}).keys()),
        **{k: w[k] for k in ("rpe", "feel", "note") if w.get(k) not in (None, "")},
    }


def _activity_brief(a: dict) -> dict:
    m = a.get("metrics") or {}
    out = {
        "id": a["id"], "date": a["date"], "sport": a["sport"], "name": a["name"],
        "minutes": _minutes(a.get("duration")), "km": round((a.get("distance") or 0) / 1000, 2),
        "tss": round(a.get("tss") or 0), "unplanned": a.get("unplanned", False), "plan": a.get("plan"),
    }
    for key in ("avg_hr", "np", "if"):
        if m.get(key):
            out[key] = round(m[key], 2)
    if m.get("hr_zones"):
        out["hr_zone_minutes"] = [_minutes(z) for z in m["hr_zones"]]
    if a.get("feedback"):
        out["feedback"] = a["feedback"]
    return out


# --- Lesen -------------------------------------------------------------------

@server.tool(annotations=READ)
def get_status() -> dict:
    """Aktueller Stand: Block der Periodisierung, Belastungs-/Entlastungswoche, Soll-Wochenstunden,
    Hitzetraining, Fitness/Ermüdung/Form (CTL/ATL/TSB), Ziel-CTL-Plan, Warnungen und Hinweise,
    dazu die Wochenstunden (Soll/erledigt/geplant) der letzten 3 und nächsten 2 Wochen."""
    rec = _api("GET", "/api/recommendations")
    status = rec["status"]
    status.pop("timeline", None)
    weeks = _api("GET", "/api/weeks")
    return {"status": status, "weeks": weeks, "today": Date.today().isoformat()}


@server.tool(annotations=READ)
def get_calendar(start: str, end: str) -> dict:
    """Geplante Workouts (mit Compliance-Farbe, Feedback) und erledigte Aktivitäten (mit Puls, NP, Zonen,
    Feedback) sowie Wettkämpfe zwischen start und end (JJJJ-MM-TT, inklusive). Für die einzelnen Schritte
    eines Workouts get_workout verwenden."""
    data = _api("GET", "/api/calendar", params={"start": start, "end": end})
    return {
        "workouts": [_workout_brief(w) for w in data["workouts"]],
        "activities": [_activity_brief(a) for a in data["activities"]],
        "races": data.get("races", []),
    }


@server.tool(annotations=READ)
def get_workout(workout_id: int) -> dict:
    """Ein Workout mit allen Schritten (Dauer in Sekunden, low/high in %), Beschreibung, Sync-Zielen und
    'nutrition': Verpflegung vorher/während/danach (KH, Flüssigkeit, Protein) für das Gewicht aus den Einstellungen,
    je Phase eine Zeile; "(Plan)" = Zahl aus dem KH-Block der Beschreibung, sonst von der App berechnet."""
    w = _api("GET", f"/api/workouts/{workout_id}")
    w["sync"] = sorted((w.get("sync") or {}).keys())  # IDs und Pfade braucht Claude nicht
    if w.get("nutrition"):
        w["nutrition"] = _nutrition_brief(w["nutrition"])
    return w


def _qty(q: dict | None) -> str:
    if not q:
        return ""
    return f"{q['low']}{'' if q['low'] == q['high'] else '–' + str(q['high'])} {q['unit']}"


def _nutrition_brief(n: dict) -> dict:
    """Ernährung kompakt: je Phase eine Zeile statt des ganzen Objekts der Detailansicht."""
    out = {"kind": n["kind_label"], "weight_kg": n["weight"]}
    for key, p in n["phases"].items():
        carbs = _qty(p.get("carbs"))
        parts = [f"KH {carbs}{' (Plan)' if p.get('source') == 'plan' else ''}" if carbs else "",
                 f"≈{_qty(p['total'])} gesamt" if p.get("total") else "",
                 f"Trinken {_qty(p.get('fluid'))}" if p.get("fluid") else "",
                 f"Protein {_qty(p.get('protein'))}" if p.get("protein") else "",
                 p.get("timing") or p.get("hint") or ""]
        out[key] = " · ".join(x for x in parts if x) or "–"
    day = n["day"]
    out["day"] = f"KH {_qty(day)} ({'–'.join(f'{v:g}' for v in day['per_kg'])} g/kg, {day['label']})"
    return out


@server.tool(annotations=READ)
def get_recommendations() -> list[dict]:
    """Vorschläge der App für die nächsten 7 Tage (mehrere pro Tag möglich) mit Begründungen.
    Jeder Vorschlag mit 'workout' kann per accept_suggestion in den Kalender übernommen werden."""
    days = _api("GET", "/api/recommendations")["days"]
    return [{
        "index": i, "date": d["date"], "weekday": d["weekday"], "kind": d["kind"], "sport": d.get("sport"),
        "name": (d.get("workout") or {}).get("name"), "tss": round(d.get("tss") or 0),
        "minutes": _minutes(sum(s.get("duration", 0) for s in _flat((d.get("workout") or {}).get("steps", [])))),
        "reasons": d["reasons"], "heat": d.get("heat", False),
    } for i, d in enumerate(days)]


def _flat(steps):
    for s in steps:
        if s.get("kind") == "repeat":
            for _ in range(int(s.get("count", 1))):
                yield from _flat(s.get("steps", []))
        else:
            yield s


@server.tool(annotations=READ)
def get_analysis(section: str = "all") -> dict:
    """Auswertungen. section: 'metrics' (Garmin: Trainingsstatus, VO2max, Endurance Score, Hitzeanpassung,
    Renn-Prognosen, FTP-Verlauf), 'power' (Leistungskurve + FTP-Schätzungen), 'efficiency' (Leistung bzw. Tempo bei
    Referenzpuls, Rad/Laufen mit Trend, letzte 10 Werte), 'zones' (Zeit in Pulszonen pro Woche) oder 'all'."""
    d = _api("GET", "/api/analysis")
    out = {
        "metrics": d.get("garmin"),
        "power": d["power_curve"],
        "efficiency": {sport: {"trend_pct_28d": v["trend"], "value": f'{v["at_ref_unit"]} bei {v["ref_hr"]} bpm (at_ref)',
                               "unit_raw_ef": v["unit"], "count": len(v["points"]), "excluded": len(v["excluded"]),
                               "last": v["points"][-10:]} for sport, v in d["efficiency"].items()},
        "zones": [{**w, "zone_minutes": [_minutes(z) for z in w.pop("zones")]} for w in d["zones"]],
    }
    if out["metrics"]:
        out["metrics"].pop("vo2max_series", None)
    return out if section == "all" else {section: out[section]}


@server.tool(annotations=READ)
def get_settings() -> dict:
    """Einstellungen: Schwellen (ftp, lthr_run, lthr_ride, threshold_pace s/km, css s/100 m, max_hr, weight),
    Wettkampf (goal_name, goal_date, race_type), week_hours, recovery_every, target_ctl, week_pattern, auto_sync."""
    s = _api("GET", "/api/settings")
    s.pop("race_plan", None)
    s["calendar_ics"] = f"{len(s.get('calendar_ics') or [])} Kalender hinterlegt"  # Links sind geheim
    return {**s, "b_c_races": _api("GET", "/api/races")}


# --- Schreiben ---------------------------------------------------------------

@server.tool(annotations=WRITE)
def create_workout(date: str, sport: str, name: str = "", description: str = "", target: str = "",
                   steps: list[dict] | str | None = None, template: str = "", minutes: int = 60,
                   circuit: dict | None = None, time: str = "", fueling: dict | None = None,
                   send_to: list[str] | None = None) -> dict:
    """Workout anlegen. Entweder `steps` oder `template` + `minutes`.

    steps – Kurzform (spart Tokens): "w15@50-75, 4x(i8@97-102, r4@50-55), c10@50-65" (w/i/r/s/c = warmup/interval/
            recovery/steady/cooldown, Zahl = Minuten, Suffix s = Sekunden, @von-bis in %) oder als Liste
            [{"kind": "warmup", "minutes": 10, "low": 65, "high": 75}, {"repeat": 4, "steps": [...]}].
            low/high in % (FTP bzw. Schwellentempo/CSS bzw. LTHR je nach target).
            Eigenes Ziel je Schritt möglich: Kurzform "w15@70-80hr, 4x(i4@103-106pace, r2@60-70hr)" bzw.
            "target": "hr" im Schritt – z. B. Einlaufen nach Puls, Intervalle nach Pace.
    time: Startzeit "07:30" (kommt vorne in den Namen). fueling: {"before", "during", "after", "day"} als Text →
            KH-Block in der Beschreibung; ohne fueling berechnet die App die Ernährung selbst.
    template: recovery, endurance, long, race_pace, tempo, sweetspot, threshold, vo2max, openers, brick, stabi, mobility.
    target: power | pace | hr (Standard je Sport) – gilt für alle Schritte ohne eigenes "target".
    circuit (Kraft/Stabi, Zirkel-Timer in der App, geht so auch an Garmin): {"work": 40, "rest": 20, "rounds": 3,
            "round_rest": 60, "exercises": ["Plank", {"name": "Bulg. Split Squat re, 3 s runter", "reps": 8},
            {"name": "Wandsitz", "seconds": 45}]} – Sekunden, rounds 1–60, eine Runde = alle Übungen einmal.
            Übung als Text = Dauer "work"; "seconds" = eigene Dauer; "reps" = Wiederholungen, weiter per „Fertig“
            ("reps": 0 = ohne feste Zahl, z. B. bis kurz vor Versagen). Hinweise wie Tempo gehören in den Namen.
    send_to: z. B. ["garmin", "intervals", "zwift", "calendar"] (calendar = Kalender-App des Macs) – nur auf Wunsch des Nutzers.
    """
    raw = {"sport": sport, "name": name, "description": description, "minutes": minutes}
    if target:
        raw["target"] = target
    if steps:
        raw["steps"] = steps
    elif template:
        raw["template"] = template
    if circuit:
        raw["circuit"] = circuit
    if time:
        raw["time"] = time
    if fueling:
        raw["fueling"] = fueling
    try:
        workout = plan_import.build_workout(raw, Date.fromisoformat(date))
    except ValueError as e:  # PlanError oder ungültiges Datum
        raise ToolError(str(e)) from None
    workout.pop("source", None)
    res = _api("POST", "/api/workouts", json=workout)
    return _send(res, send_to)


def _send(res: dict, send_to: list[str] | None) -> dict:
    workout, errors = res["workout"], dict(res.get("errors") or {})
    missing = [t for t in (send_to or []) if t not in (workout.get("sync") or {})]
    if missing:
        sent = _api("POST", f"/api/workouts/{workout['id']}/sync", json={"targets": missing})
        workout, errors = sent["workout"], {**errors, **sent["errors"]}
    return {"workout": _workout_brief(workout), "errors": errors}


@server.tool(annotations=WRITE)
def update_workout(workout_id: int, date: str = "", name: str = "", description: str = "", target: str = "",
                   steps: list[dict] | str | None = None, status: str = "", rpe: float | None = None,
                   feel: int | None = None, note: str = "", circuit: dict | None = None,
                   send_to: list[str] | None = None) -> dict:
    """Workout ändern (nur angegebene Felder). steps und circuit im selben Format wie bei create_workout.
    target: power | pace | hr für alle Schritte ohne eigenes Ziel; eigenes Ziel je Schritt über die steps
    (Kurzform "i20s@95-103pace", Liste "target": "pace").
    status: planned | done. rpe 0–10, feel 1–5. Bereits übertragene Workouts werden auf den Geräten aktualisiert."""
    w = _api("GET", f"/api/workouts/{workout_id}")
    w.pop("nutrition", None)
    if target:
        if target not in plan_import.TARGETS:
            raise ToolError(f"Unbekanntes Ziel {target!r} (erlaubt: {', '.join(plan_import.TARGETS)})")
        w["target"] = target
    if steps:
        try:
            w["steps"] = plan_import.build_workout({"sport": w["sport"], "steps": steps}, Date.today())["steps"]
        except plan_import.PlanError as e:
            raise ToolError(str(e)) from None
    if circuit:
        try:
            w["circuit"] = plan_import.parse_circuit(circuit, "Workout")
        except plan_import.PlanError as e:
            raise ToolError(str(e)) from None
    for key, value in (("date", date), ("name", name), ("description", description), ("status", status), ("note", note)):
        if value:
            w[key] = value
    if rpe is not None:
        w["rpe"] = rpe
    if feel is not None:
        w["feel"] = feel
    return _send(_api("POST", "/api/workouts", json=w), send_to)


@server.tool(annotations=DELETE)
def delete_workout(workout_id: int) -> dict:
    """Workout löschen – auch auf Garmin/Wahoo/Zwift, falls es dorthin übertragen wurde."""
    return _api("DELETE", f"/api/workouts/{workout_id}")


@server.tool(annotations=WRITE)
def accept_suggestion(index: int, send_to: list[str] | None = None) -> dict:
    """Einen Vorschlag aus get_recommendations (per index) als Workout in den Kalender übernehmen."""
    days = _api("GET", "/api/recommendations")["days"]
    if not 0 <= index < len(days) or not days[index].get("workout"):
        raise ToolError("Kein Vorschlag mit Workout an dieser Stelle – erst get_recommendations aufrufen.")
    d = days[index]
    return _send(_api("POST", "/api/workouts", json={**d["workout"], "date": d["date"]}), send_to)


@server.tool(annotations=WRITE)
def import_plan(plan: dict | None = None, start: str = "", replace: bool = False, dry_run: bool = True,
                preview_id: str = "") -> dict:
    """Trainingsplan (z. B. 4-Wochen-Block) im JSON-Format der App prüfen bzw. importieren.

    Format: {"name": "...", "weeks": [{"week": 1, "days": {"mon": [Workout, ...], ...}}]} – Workouts wie bei
    create_workout (sport, name, time, steps in Kurzform oder template + minutes, optional fueling).
    start = Montag der 1. Woche (sonst nächster Montag). replace=True ersetzt geplante Workouts im Zeitraum.
    Tokens sparen: zuerst mit plan prüfen (dry_run=True, Standard) – die Antwort enthält eine preview_id. Dann nur
    import_plan(preview_id=…) aufrufen, statt den ganzen Plan noch einmal zu senden. Den Auftragstext mit allen
    Vorgaben (Soll-Stunden, Wochenmuster, Schwellen) liefert get_plan_brief.
    """
    if preview_id:
        params = {} if replace is False else {"replace": True}
        return _api("POST", f"/api/plan/import/{preview_id}", params=params)
    if not plan:
        raise ToolError("plan oder preview_id angeben.")
    body = {"plan": plan, "start": start or None, "replace": replace}
    if dry_run:
        res = _api("POST", "/api/plan/preview", json=body)
        weeks: dict[str, dict] = {}
        for w in res["workouts"]:  # kompakte Vorschau: je Woche Stunden und Einheiten statt aller Details
            week = weeks.setdefault(Date.fromisoformat(w["date"]).strftime("KW %V"), {"hours": 0.0, "workouts": []})
            week["hours"] += w["duration"] / 3600
            week["workouts"].append(f"{w['date'][5:]} {w['sport']} {w['name']} {_minutes(w['duration'])}′ "
                                    f"{round(w['tss'])} TSS")
        return {"preview_id": res["preview_id"], "start": res["start"], "end": res["end"],
                "weeks": {k: {**v, "hours": round(v["hours"], 1)} for k, v in weeks.items()},
                "existing_planned_in_range": res["existing"], "warnings": res["warnings"],
                "hint": "Zum Importieren import_plan(preview_id=…) aufrufen (replace=True ersetzt Geplantes)."}
    return _api("POST", "/api/plan/import", json=body)


@server.tool(annotations=READ)
def get_plan_brief(start: str = "", weeks: int = 4, notes: str = "") -> str:
    """Kompakter Auftragstext für einen Trainingsblock: Schwellen, Gewicht, Saisonziel, Soll-Stunden und Blockfokus
    je Woche, eigenes Wochenmuster (falls gesetzt), Verfügbarkeit und belegte Zeiten aus den hinterlegten Kalendern
    (nur Uhrzeiten), Wettkämpfe, Zonen und das Kurzformat. Ersetzt get_status + get_settings (und das Abfragen von
    Kalenderterminen) beim Planen eines Blocks. start = Montag (Standard: nächster Montag), weeks 1–8,
    notes = zusätzliche Angaben zur Verfügbarkeit (sonst die gespeicherten)."""
    params = {"start": start, "weeks": weeks, **({"notes": notes} if notes else {})}
    return _api("GET", "/api/plan/prompt", params=params, text=True)


@server.tool(annotations=WRITE)
def set_activity_feedback(activity_id: str, rpe: float | None = None, feel: int | None = None, note: str = "") -> dict:
    """Feedback zu einer erledigten Aktivität (id aus get_calendar, z. B. 'garmin:123'): rpe 0–10, feel 1–5, Notiz.
    Fließt in die Vorschläge ein. Alle Felder leer = Feedback löschen."""
    return _api("PUT", f"/api/activities/{quote(activity_id, safe='')}/feedback", json={"rpe": rpe, "feel": feel, "note": note})


@server.tool(annotations=DELETE)
def delete_activity(activity_id: str) -> dict:
    """Importierte Aktivität (id aus get_calendar, z. B. 'garmin:123') aus der App löschen, etwa wenn dieselbe Einheit
    doppelt hochgeladen wurde (Zwift und Garmin-Uhr). Bleibt bei Garmin bestehen, wird aber nicht erneut importiert."""
    return _api("DELETE", f"/api/activities/{quote(activity_id, safe='')}")


SETTABLE = {"ftp", "lthr_run", "lthr_ride", "max_hr", "threshold_pace", "css", "weight", "sweat_rate", "goal_name", "goal_date",
            "race_type", "week_hours", "recovery_every", "cycle_start", "taper_weeks", "target_ctl", "week_pattern",
            "auto_sync", "garmin_profile", "mac_calendar", "availability", "calendar_ics", "own_spacing_rules"}


@server.tool(annotations=WRITE)
def update_settings(values: dict) -> dict:
    """Einstellungen ändern, z. B. {"week_hours": 10, "target_ctl": 105} oder {"css": 86}.
    Erlaubt: ftp, lthr_run, lthr_ride, max_hr, threshold_pace (s/km), css (s/100 m), weight, sweat_rate (l/h), goal_name, goal_date,
    race_type (ironman|half|other), week_hours, recovery_every, cycle_start (Montag der 1. Belastungswoche, "" = vom
    Wettkampf rückwärts), taper_weeks (0 = Standard), target_ctl, week_pattern, auto_sync (garmin, intervals, zwift,
    calendar), garmin_profile, mac_calendar (Name des Kalenders in der Kalender-App des Macs für Trainings),
    own_spacing_rules (True = keine 48-h-/eine-harte-pro-Tag-Regel in Vorschlägen und Plan-Brief; Abstände regelt der Nutzer).
    Achtung: Mit garmin_profile=True überschreibt Garmin FTP/LTHR/Schwellentempo beim nächsten Öffnen."""
    unknown = set(values) - SETTABLE
    if unknown:
        raise ToolError(f"Nicht änderbar: {', '.join(sorted(unknown))}")
    s = _api("PUT", "/api/settings", json=values)
    return {k: s[k] for k in values}


@server.tool(annotations=WRITE)
def add_race(name: str, date: str, priority: str = "B", race_type: str = "other") -> dict:
    """Weiteren Wettkampf eintragen. priority: B (Mini-Taper + Erholung) oder C (durchtrainieren, kürzere Erholung).
    race_type: run_5k, run_10k, run_half, run_marathon, run_ultra, tri_sprint, tri_olympic, half (70.3), ironman,
    ride, other – bestimmt Taper, Erholungstage und Laufpause. Das A-Rennen ist goal_name/goal_date in den Einstellungen."""
    return _api("POST", "/api/races", json={"name": name, "date": date, "priority": priority, "race_type": race_type})


@server.tool(annotations=DELETE)
def delete_race(race_id: int) -> dict:
    """B/C-Wettkampf entfernen (id aus get_settings → b_c_races)."""
    return _api("DELETE", f"/api/races/{race_id}")


@server.tool(annotations=WRITE)
def send_planned_workouts(target: str, days: int = 120, resend: bool = False) -> dict:
    """Alle geplanten, noch nicht übertragenen Workouts der nächsten `days` Tage an ein Ziel senden:
    garmin, intervals (→ Wahoo), zwift oder calendar (Kalender-App des Macs). resend=True sendet auch schon
    übertragene erneut (z. B. Kalendertermine reparieren). Nur auf Wunsch des Nutzers."""
    return _api("POST", "/api/sync/bulk", json={"target": target, "days": days, "resend": resend})


@server.tool(annotations=READ)
def check_race_conflicts() -> list[dict]:
    """Geplante Workouts, die nicht zu einem Wettkampf passen (Taper, Renntag, Regeneration, Erholung, Laufpause –
    Regeln je Distanz und Priorität). Pro Konflikt: Problem, Aktion (update/delete) und konkreter Vorschlag.
    Ändert nichts – zum Übernehmen resolve_race_conflicts verwenden."""
    return [{
        **{k: c[k] for k in ("workout_id", "date", "sport", "name", "minutes", "race", "phase", "problem", "action")},
        "proposal": None if not c["proposal"] else {
            "sport": c["proposal"]["sport"], "name": c["proposal"]["name"], "minutes": _minutes(c["proposal"]["duration"]),
            "template": c["proposal"].get("template"), "tss": round(c["proposal"]["tss"]),
        },
    } for c in _api("GET", "/api/conflicts")]


@server.tool(annotations=DELETE)
def resolve_race_conflicts(workout_ids: list[int]) -> dict:
    """Vorschläge aus check_race_conflicts für die genannten Workouts übernehmen (ändern oder löschen, auch auf
    Garmin/Wahoo/Zwift, falls übertragen). Nur nach Zustimmung des Nutzers aufrufen. Alternativ einzelne Workouts
    mit update_workout individuell anpassen."""
    return _api("POST", "/api/conflicts/apply", json={"workout_ids": workout_ids})


@server.tool(annotations=WRITE)
def import_activities(days: int = 14) -> dict:
    """Erledigte Aktivitäten der letzten `days` Tage von Garmin (und intervals.icu, falls eingerichtet) holen."""
    status = _api("GET", "/api/status")
    result = {}
    for source in ("garmin", "intervals"):
        if status.get(source):
            result[source] = _api("POST", f"/api/import/{source}", params={"days": days})["imported"]
    return result or {"hint": "Weder Garmin noch intervals.icu verbunden."}


if __name__ == "__main__":
    server.run("stdio")
