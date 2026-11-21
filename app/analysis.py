"""Analysen aus den importierten Aktivitäten (ohne Sekundendaten – Garmin-Zusammenfassungen reichen).

- Efficiency Factor (EF): Rad NP / Ø-Puls, Laufen steigungsbereinigtes Tempo (m/min) / Ø-Puls.
  Nur gleichmäßige, lockere Einheiten sind vergleichbar (sonst misst EF die Intensität, nicht die Form).
- Zeit in Pulszonen pro Woche (Schwimmen/Rad/Laufen), Anteil locker (Z1–2) vs. intensiv (Z3–5).
- Leistungskurve: beste Durchschnittsleistung je Dauer, letzte 90 Tage vs. 365 Tage, plus FTP-Schätzungen.
"""
from datetime import date, timedelta

from .periodization import monday
from .templates import ENDURANCE_SPORTS

EF_MIN_SECONDS = {"ride": 45 * 60, "run": 30 * 60}
EF_MAX_IF = 0.80            # Rad: nur lockere Fahrten
EF_MAX_HARD_SHARE = 0.10    # Laufen: höchstens 10 % in Zone 4–5


def efficiency(a: dict) -> float | None:
    m = a.get("metrics") or {}
    if not m.get("avg_hr"):
        return None
    if a["sport"] == "ride" and m.get("np"):
        return m["np"] / m["avg_hr"]
    speed = m.get("gap") or m.get("speed")
    if a["sport"] == "run" and speed:
        return speed * 60 / m["avg_hr"]
    return None


def _steady(a: dict) -> bool:
    m = a.get("metrics") or {}
    if (a.get("duration") or 0) < EF_MIN_SECONDS.get(a["sport"], 10**9):
        return False
    if a["sport"] == "ride":
        return (m.get("if") or 1) < EF_MAX_IF
    zones = m.get("hr_zones")
    return bool(zones and sum(zones)) and (zones[3] + zones[4]) / sum(zones) <= EF_MAX_HARD_SHARE


def ef_series(activities: list[dict], today: date) -> dict:
    """Pro Sport: Punkte {date, ef, name} und Trend (Ø letzte 28 Tage vs. 28 Tage davor in %)."""
    out = {}
    for sport in ("ride", "run"):
        points = [{"date": a["date"], "ef": round(efficiency(a), 3), "name": a["name"]}
                  for a in activities if a["sport"] == sport and _steady(a) and efficiency(a)]
        recent = [p["ef"] for p in points if p["date"] > (today - timedelta(days=28)).isoformat()]
        before = [p["ef"] for p in points
                  if (today - timedelta(days=56)).isoformat() < p["date"] <= (today - timedelta(days=28)).isoformat()]
        trend = None
        if recent and before:
            trend = round((sum(recent) / len(recent)) / (sum(before) / len(before)) * 100 - 100, 1)
        out[sport] = {"points": points, "trend": trend, "unit": "W/bpm" if sport == "ride" else "m/min/bpm"}
    return out


def zone_weeks(activities: list[dict], today: date, weeks: int = 8) -> list[dict]:
    """Sekunden in Pulszone 1–5 pro Woche (Ausdauersportarten), älteste Woche zuerst."""
    first = monday(today) - timedelta(weeks=weeks - 1)
    out = []
    for i in range(weeks):
        start = first + timedelta(weeks=i)
        end = (start + timedelta(days=6)).isoformat()
        zones = [0] * 5
        for a in activities:
            z = (a.get("metrics") or {}).get("hr_zones")
            if z and a["sport"] in ENDURANCE_SPORTS and start.isoformat() <= a["date"] <= end:
                zones = [x + y for x, y in zip(zones, z)]
        total = sum(zones)
        out.append({"week_start": start.isoformat(), "zones": zones,
                    "low_pct": round((zones[0] + zones[1]) / total * 100) if total else None})
    return out


def power_curve(activities: list[dict], today: date, ftp: float) -> dict:
    """Beste Leistung je Dauer (Rad) für 90 und 365 Tage, dazu FTP-Schätzungen aus den 90 Tagen."""
    def best(days: int) -> dict[int, dict]:
        since = (today - timedelta(days=days)).isoformat()
        out: dict[int, dict] = {}
        for a in activities:
            if a["sport"] != "ride" or a["date"] < since:
                continue
            for d, watts in ((a.get("metrics") or {}).get("mmp") or {}).items():
                if watts > out.get(int(d), {}).get("watts", 0):
                    out[int(d)] = {"watts": watts, "date": a["date"], "name": a["name"]}
        return out

    recent, year = best(90), best(365)
    estimates = []
    if 1200 in recent:
        estimates.append({"method": "95 % der besten 20 min", "watts": round(recent[1200]["watts"] * 0.95)})
    if 300 in recent and 1200 in recent:  # Critical Power aus 5 und 20 min (2-Parameter-Modell)
        cp = (recent[1200]["watts"] * 1200 - recent[300]["watts"] * 300) / (1200 - 300)
        estimates.append({"method": "Critical Power (5 + 20 min)", "watts": round(cp)})
    if 3600 in recent:
        estimates.append({"method": "Beste 60 min", "watts": round(recent[3600]["watts"])})
    as_list = lambda curve: [{"duration": d, **v} for d, v in sorted(curve.items())]  # noqa: E731
    return {"recent": as_list(recent), "year": as_list(year), "ftp": ftp, "estimates": estimates}
