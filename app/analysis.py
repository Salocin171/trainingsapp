"""Analysen aus den importierten Aktivitäten (ohne Sekundendaten – Garmin-Zusammenfassungen reichen).

- Efficiency Factor (EF): Rad NP / Ø-Puls, Laufen steigungsbereinigtes Tempo (m/min) / Ø-Puls.
  Der rohe EF steigt mit der Intensität (Puls = Sockel + Steigung × Leistung), deshalb wird jede
  vergleichbare Einheit zusätzlich auf einen festen Referenzpuls umgerechnet:
      Leistung bei Referenzpuls = NP + (Referenzpuls − Ø-Puls) / Steigung
  Die Steigung (bpm pro W bzw. pro m/min) wird aus den eigenen Einheiten geschätzt. Der Trend
  nutzt diesen Wert („W bei 140 bpm“, „Tempo bei 145 bpm“), nicht den rohen EF.
- Nur gleichmäßige Grundlageneinheiten zählen. Regeln: siehe EF_* unten und _not_comparable().
- Zeit in Pulszonen pro Woche (Schwimmen/Rad/Laufen), Anteil locker (Z1–2) vs. intensiv (Z3–5).
- Leistungskurve: beste Durchschnittsleistung je Dauer, letzte 90 Tage vs. 365 Tage, plus FTP-Schätzungen.

Optionale Felder (werden genutzt, wenn der Import sie liefert, sonst wird die Regel übersprungen):
  m["start_time"] (ISO-Datum mit Uhrzeit), m["indoor"], m["event_type"], m["anaerobic_te"], m["temp"],
  m["elevation_gain"] (m), a["distance"] (m). Garmin liefert alle (siehe sync/garmin.activity_metrics).
"""
from datetime import date, datetime, timedelta
from statistics import median

from .periodization import monday
from .templates import ENDURANCE_SPORTS

# --- Regeln für den EF-Verlauf -------------------------------------------------------------------
EF_DURATION = {"ride": (45 * 60, 3 * 3600), "run": (30 * 60, 90 * 60)}  # min/max – länger = Puls-Drift
EF_IF_RANGE = (0.45, 0.80)      # Rad: NP in % der FTP. Untergrenze tiefer als vorher, weil jetzt normiert wird
EF_MAX_VI = {"indoor": 1.05, "outdoor": 1.12}  # NP / Ø-Leistung. Rolle ist von Natur aus gleichmäßig
EF_MAX_HARD_SHARE = 0.10        # höchstens 10 % der Zeit in Pulszone 4–5
EF_MIN_STEADY_SHARE = 0.75      # mind. 75 % der Zeit in zwei benachbarten Pulszonen
EF_MAX_ANAEROBIC_TE = 1.5       # Garmin anaerober Trainingseffekt – ab hier waren Intervalle/Antritte drin
EF_MAX_TEMP = 28                # °C, nur draußen. Uhrsensor (Minimum) liegt über der Lufttemperatur – bei 25 °C fielen fast alle Sommerläufe raus, ohne sichtbar schlechtere Werte
EF_BRICK_GAP = 60 * 60          # Lauf startet bis 60 min nach Radende → Koppellauf
EF_RUN_MAX_CLIMB = 10           # Hm/km – darüber ohne GAP nicht vergleichbar
EF_MAX_HR_OFFSET = 15           # bpm: so weit darf der Ø-Puls vom Referenzpuls weg sein
# Puls-Steigung relativ zur eigenen Schwelle (bpm pro 100 % FTP bzw. pro Schwellentempo), damit die Werte
# für jedes Leistungsniveau passen: 110 bpm pro FTP = 0,29 bpm/W bei FTP 385, aber 0,55 bpm/W bei FTP 200.
EF_SLOPE_DEFAULT = {"ride": 110, "run": 150}   # falls zu wenig eigene Daten
EF_SLOPE_RANGE = {"ride": (40, 230), "run": (50, 300)}
EF_SCALE_FALLBACK = {"ride": 250, "run": 250}  # W bzw. m/min (4:00/km), wenn FTP/Schwellentempo fehlen
EF_SLOPE_PAIR_DAYS = 42         # Steigung nur aus Paaren innerhalb von 6 Wochen (gleiche Form)
EF_SLOPE_MIN_PAIRS = 15
EF_TREND_DAYS = 28
EF_TREND_MIN_POINTS = 3

INDOOR_WORDS = ("zwift", "indoor", "rolle", "trainer", "virtual", "laufband", "treadmill", "mywhoosh", "rouvy")


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


def _output(a: dict) -> float | None:
    """Rad: NP in W, Laufen: (steigungsbereinigtes) Tempo in m/min."""
    m = a.get("metrics") or {}
    if a["sport"] == "ride":
        return m.get("np")
    speed = m.get("gap") or m.get("speed")
    return speed * 60 if speed else None


def _is_indoor(a: dict) -> bool:
    m = a.get("metrics") or {}
    for flag in (a.get("indoor"), m.get("indoor")):
        if flag is not None:
            return bool(flag)
    text = f'{a.get("sub_sport") or ""} {a.get("name") or ""}'.lower()
    return any(w in text for w in INDOOR_WORDS)


def _is_race(a: dict) -> bool:
    m = a.get("metrics") or {}
    return bool(a.get("race")) or str(m.get("event_type") or "").lower() == "race"


def _start(a: dict) -> datetime | None:
    raw = a.get("start_time") or (a.get("metrics") or {}).get("start_time")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _ftp_on(day: str, ftp) -> float:
    """FTP am Tag der Einheit. ftp: Zahl oder Liste [{"date": "2026-03-01", "watts": 360}, ...]."""
    if not isinstance(ftp, (list, tuple)):
        return ftp or 0
    history = sorted(ftp, key=lambda e: e["date"])
    valid = [e["watts"] for e in history if e["date"] <= day]
    return valid[-1] if valid else (history[0]["watts"] if history else 0)


def _days_between(d1: str, d2: str) -> int:
    return abs((date.fromisoformat(d1[:10]) - date.fromisoformat(d2[:10])).days)


def _not_comparable(a: dict, ftp: float, after_ride: bool = False) -> str | None:
    """Grund, warum die Einheit für den EF-Verlauf nicht vergleichbar ist (None = zählt).

    Beispiel: 1 h Intervalle + 1 h locker – die NP bleibt hoch, der Ø-Puls sinkt durch den lockeren Teil,
    der EF wirkt dadurch viel besser als die Form. Solche Einheiten fallen über VI, Pulszonen-Verteilung
    und anaeroben Trainingseffekt heraus.
    """
    m = a.get("metrics") or {}
    sport = a["sport"]
    indoor = _is_indoor(a)
    duration = a.get("duration") or 0

    if _is_race(a):
        return "Wettkampf"
    if duration > EF_DURATION[sport][1]:
        return f"zu lang ({duration / 3600:.1f} h, Puls-Drift)"
    if sport == "run" and after_ride:
        return "Koppellauf (Puls vom Radfahren erhöht)"
    if not indoor and m.get("temp") is not None and m["temp"] > EF_MAX_TEMP:
        return f"warm ({m['temp']:.0f} °C)"

    te = m.get("anaerobic_te")
    if te is not None and te >= EF_MAX_ANAEROBIC_TE:
        return f"Intervalle/Antritte (anaerober Trainingseffekt {te:.1f})"

    if sport == "ride":
        if ftp:
            intensity = m["np"] / ftp
            if intensity < EF_IF_RANGE[0]:
                return f"zu locker ({intensity * 100:.0f} % FTP)"
            if intensity >= EF_IF_RANGE[1]:
                return f"zu intensiv ({intensity * 100:.0f} % FTP)"
        if m.get("avg_power"):
            vi = m["np"] / m["avg_power"]
            if vi > EF_MAX_VI["indoor" if indoor else "outdoor"]:
                return f"ungleichmäßig (NP {vi * 100 - 100:.0f} % über Ø-Leistung)"
    else:
        if indoor:
            return "Laufband (Tempo unzuverlässig)"
        distance = m.get("distance") or a.get("distance")
        if not m.get("gap") and m.get("elevation_gain") is not None and distance:
            climb = m["elevation_gain"] / (distance / 1000)
            if climb > EF_RUN_MAX_CLIMB:
                return f"hügelig ohne GAP ({climb:.0f} Hm/km)"

    zones = m.get("hr_zones")
    total = sum(zones) if zones else 0
    if not total:
        return "keine Pulszonen" if sport == "run" else None
    hard = (zones[3] + zones[4]) / total
    if hard > EF_MAX_HARD_SHARE:
        return f"{hard * 100:.0f} % in Zone 4–5"
    steady = max(zones[i] + zones[i + 1] for i in range(4)) / total
    if steady < EF_MIN_STEADY_SHARE:
        return f"Puls ungleichmäßig (nur {steady * 100:.0f} % in zwei Nachbarzonen)"
    return None


def _hr_slope(points: list[dict], sport: str, scale: float) -> float:
    """Wie viele bpm der Puls pro W (bzw. m/min) steigt – Median aller Paarsteigungen (Theil-Sen),
    nur aus Einheiten, die höchstens 6 Wochen auseinanderliegen, damit Formänderungen nicht hineinrechnen.

    Geschätzt in beide Richtungen (Puls über Leistung und Leistung über Puls), Ergebnis = geometrisches Mittel.
    Grund: Läufe und Ausfahrten draußen sind oft nach Gefühl/Puls gelaufen – dann streut die Leistung und
    die Steigung „Puls über Leistung“ allein fällt zu flach aus (in echten Daten etwa um ein Drittel),
    die Umrechnung auf den Referenzpuls würde überkorrigieren."""
    hr_on_x, x_on_hr = [], []
    for i, p in enumerate(points):
        for q in points[i + 1:]:
            if _days_between(p["date"], q["date"]) > EF_SLOPE_PAIR_DAYS:
                continue
            dx, dhr = q["x"] - p["x"], q["hr"] - p["hr"]
            if abs(dx) >= 0.08 * max(p["x"], q["x"]):
                hr_on_x.append(dhr / dx)
            if abs(dhr) >= 4:
                x_on_hr.append(dx / dhr)
    scale = scale or EF_SCALE_FALLBACK[sport]
    default = EF_SLOPE_DEFAULT[sport] / scale
    if len(hr_on_x) < EF_SLOPE_MIN_PAIRS or len(x_on_hr) < EF_SLOPE_MIN_PAIRS:
        return default
    a, b = median(hr_on_x), median(x_on_hr)
    if a <= 0 or b <= 0:
        return default
    lo, hi = (v / scale for v in EF_SLOPE_RANGE[sport])
    return min(max((a / b) ** 0.5, lo), hi)


def _trend(points: list[dict], today: date, key: str) -> dict:
    """Median der letzten 28 Tage vs. 28 Tage davor in %. Unter 3 Punkten je Fenster kein Trend."""
    cut1 = (today - timedelta(days=EF_TREND_DAYS)).isoformat()
    cut2 = (today - timedelta(days=2 * EF_TREND_DAYS)).isoformat()
    recent = [p[key] for p in points if p["date"] > cut1]
    before = [p[key] for p in points if cut2 < p["date"] <= cut1]
    pct = None
    if len(recent) >= EF_TREND_MIN_POINTS and len(before) >= EF_TREND_MIN_POINTS:
        pct = round(median(recent) / median(before) * 100 - 100, 1)
    return {"trend": pct, "n_recent": len(recent), "n_before": len(before)}


def ef_series(activities: list[dict], today: date, ftp=0, threshold_pace: float = 0) -> dict:
    """Pro Sport: vergleichbare Punkte, nicht gezählte Einheiten mit Grund und Trend.

    Punkte: {date, name, ef (roh), at_ref (W bzw. m/min beim Referenzpuls), ef_adj (at_ref / Referenzpuls)}.
    ftp: aktuelle FTP oder FTP-Verlauf (Liste {date, watts}) – dann zählt die FTP am Tag der Einheit.
    threshold_pace: Schwellentempo Laufen in s/km – skaliert wie die FTP die Grenzen der Puls-Steigung.
    """
    scale = {"ride": _ftp_on(today.isoformat(), ftp), "run": 60000 / threshold_pace if threshold_pace else 0}
    ride_ends = []
    for a in activities:
        start = _start(a)
        if a["sport"] == "ride" and start:
            ride_ends.append(start + timedelta(seconds=a.get("duration") or 0))

    def after_ride(a: dict) -> bool:
        start = _start(a)
        return bool(start) and any(timedelta(0) <= start - end <= timedelta(seconds=EF_BRICK_GAP) for end in ride_ends)

    out = {}
    for sport in ("ride", "run"):
        candidates, excluded = [], []
        for a in activities:
            ef = efficiency(a) if a["sport"] == sport else None
            if not ef or (a.get("duration") or 0) < EF_DURATION[sport][0]:
                continue
            p = {"date": a["date"], "ef": round(ef, 3), "name": a["name"]}
            reason = _not_comparable(a, _ftp_on(a["date"], ftp), after_ride(a) if sport == "run" else False)
            if reason:
                excluded.append({**p, "reason": reason})
            else:
                candidates.append({**p, "x": _output(a), "hr": a["metrics"]["avg_hr"]})

        slope = _hr_slope(candidates, sport, scale[sport])
        ref_hr = round(median(c["hr"] for c in candidates) / 5) * 5 if candidates else None
        points = []
        for c in candidates:
            base = {"date": c["date"], "ef": c["ef"], "name": c["name"]}
            offset = ref_hr - c["hr"]
            if abs(offset) > EF_MAX_HR_OFFSET:
                excluded.append({**base, "reason": f"Ø-Puls {c['hr']:.0f} zu weit vom Referenzpuls {ref_hr}"})
                continue
            at_ref = c["x"] + offset / slope
            points.append({**base, "at_ref": round(at_ref, 1), "ef_adj": round(at_ref / ref_hr, 3)})

        points.sort(key=lambda p: p["date"])
        excluded.sort(key=lambda p: p["date"])
        out[sport] = {"points": points, "excluded": excluded, **_trend(points, today, "at_ref"),
                      "ref_hr": ref_hr, "slope": round(slope, 3),
                      "unit": "W/bpm" if sport == "ride" else "m/min/bpm",
                      "at_ref_unit": "W" if sport == "ride" else "m/min"}
    current_ftp = _ftp_on(today.isoformat(), ftp)
    out["ride"]["np_range"] = [round(current_ftp * f) for f in EF_IF_RANGE] if current_ftp else None
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
