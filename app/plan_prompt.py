"""KI-Auftrag für einen Trainingsblock: alles, was eine beliebige KI (ChatGPT, Gemini, Claude ohne MCP …) braucht,
um einen Plan als JSON für den Import zu schreiben – Athletenwerte, Soll-Stunden je Woche aus der Periodisierung,
Wochenmuster, Wettkämpfe und ein kompaktes Format (Kurzform für Schritte, Ernährung rechnet die App selbst).

Bewusst knapp gehalten: Je kürzer Auftrag und Antwort, desto weniger Tokens.
"""
from datetime import date, timedelta

from . import periodization, races as race_effects
from .templates import TEMPLATES, ZONES

SPORT_DE = {"swim": "Schwimmen", "ride": "Rad", "run": "Laufen", "strength": "Kraft/Stabi", "mobility": "Mobility/Yoga"}
TYPE_DE = {"recovery": "Regeneration", "easy": "locker", "hard": "hart", "long": "lang"}
WEEKDAYS = [("mon", "Mo"), ("tue", "Di"), ("wed", "Mi"), ("thu", "Do"), ("fri", "Fr"), ("sat", "Sa"), ("sun", "So")]
RACE_TYPES = {"ironman": "Langdistanz", "half": "Mitteldistanz (70.3)", "other": "Wettkampf"}


def _pace(sec: float) -> str:
    sec = round(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def _hours(h: float) -> str:
    return f"{h:.1f}".replace(".", ",") + " h"


def _num(value) -> str:
    return f"{float(value):g}".replace(".", ",") if value else ""


def _zones(sport: str) -> str:
    z = ZONES[sport]
    names = [("rec", "Reg"), ("endu", "locker"), ("race", "Renntempo"), ("tempo", "Tempo"), ("ss", "SweetSpot"),
             ("thr", "Schwelle"), ("vo2", "VO2max")]
    return ", ".join(f"{label} {z[k][0]}-{z[k][1]}" for k, label in names)


def build(settings: dict, start: date, weeks: int, race_list: list[dict], ctl: float | None = None,
          past_hours: list[float] | None = None) -> str:
    """Auftragstext für `weeks` Wochen ab dem Montag `start`."""
    s = settings
    lines = ["Du bist erfahrene*r Triathlon-Trainer*in. Erstelle meinen nächsten Trainingsblock als JSON für meine "
             "Trainingsapp. Antworte NUR mit dem JSON, ohne Erklärungen.", "", "## Ich"]
    lines.append(f"Gewicht {_num(s.get('weight')) or '?'} kg · FTP {s['ftp']} W · Schwelle Laufen {_pace(s['threshold_pace'])}/km"
                 f" · CSS {_pace(s['css'])}/100 m · LTHR Rad {s['lthr_ride']} / Laufen {s['lthr_run']} · "
                 f"Max-Puls {s['max_hr']}")
    if s.get("goal_date"):
        days = (date.fromisoformat(s["goal_date"]) - start).days
        lines.append(f"Saisonziel: {s.get('goal_name') or 'Wettkampf'} ({RACE_TYPES.get(s.get('race_type'), 'Wettkampf')}) "
                     f"am {date.fromisoformat(s['goal_date']):%d.%m.%Y}, {days // 7} Wochen nach Blockbeginn")
    if ctl is not None:
        recent = f", Ausdauerstunden der letzten Wochen (älteste zuerst): {' / '.join(_hours(h) for h in past_hours)}" if past_hours else ""
        lines.append(f"Fitness (CTL) aktuell {round(ctl)}{recent}")

    lines += ["", "## Vorgaben der App je Woche (Soll = Schwimmen + Rad + Laufen; Kraft/Mobility zusätzlich)"]
    end = start + timedelta(weeks=weeks, days=-1)
    for i in range(weeks):
        monday = start + timedelta(weeks=i)
        info = periodization.week_info(s, monday)
        kind = "Entlastungswoche" if info["recovery"] else "Rennwoche" if info["race_week"] else \
            f"Belastung {info['cycle_week']}/{info['cycle_len']}" if info["cycle_week"] else "Belastung"
        extra = f" · {info['heat_sessions']} Hitzeeinheiten (locker, warm, ohne Ventilator)" if info["heat"] else ""
        lines.append(f"- Woche {i + 1} (ab {monday:%d.%m.}): {info['block_name']}, {kind}, Soll {_hours(info['target_hours'])}"
                     f" – {info['focus']}{extra}")

    pattern = s.get("week_pattern") or {}
    lines += ["", "## Wochenmuster (Einheiten je Tag; leer = Ruhetag)"]
    lines.append(" · ".join(f"{label}: " + (", ".join(f"{SPORT_DE.get(x['sport'], x['sport'])} {TYPE_DE.get(x['type'], x['type'])}"
                                                      for x in pattern.get(key, [])) or "Ruhe")
                           for key, label in WEEKDAYS))

    in_range = [r for r in race_list if start.isoformat() <= r["date"] <= (end + timedelta(days=14)).isoformat()]
    if in_range:
        lines += ["", "## Wettkämpfe im Zeitraum"]
        for r in in_range:
            p = race_effects.profile(r)
            note = f" – {p['taper']} Tage locker davor, danach {p['rest']} Tage Ruhe und {p['recovery']} Tage nur locker"
            lines.append(f"- {date.fromisoformat(r['date']):%d.%m.%Y} {r['name']} ({r.get('priority', 'A')}){note}")

    lines += ["", "## Regeln",
              "- Soll-Stunden je Woche ±10 % einhalten, Wochenmuster als Grundgerüst; ca. 80 % locker.",
              "- Harte Einheiten nicht an zwei Tagen hintereinander; Entlastungswoche wirklich locker.",
              "- Wettkämpfe: Tag davor kurz mit Steigerungen, danach Erholung.",
              "- Ernährung NICHT angeben – die App berechnet Kohlenhydrate, Trinken und Eiweiß selbst.",
              "", "## JSON-Format (genau so)",
              f'{{"name":"Block ab {start:%d.%m.}","start":"{start.isoformat()}","weeks":[{{"week":1,"days":{{'
              '"tue":[W,W],"sat":[W]}}]}',
              'W = {"sport":"ride","name":"Schwelle 4x8","time":"07:00","steps":"w15@50-75, 4x(i8@97-102, r4@50-55), '
              'c10@50-65"}',
              '  oder {"sport":"run","template":"endurance","minutes":60,"name":"Lauf locker"}',
              '  Kraft: {"sport":"strength","template":"stabi","minutes":40} · Mobility: {"sport":"mobility",'
              '"template":"mobility","minutes":25}',
              "- sport: swim | ride | run | strength | mobility. Tage: mon…sun. \"time\" und \"description\" (kurz) optional.",
              "- steps (Kurzform): w=Einwärmen, i=Intervall, r=Erholung, s=Konstant, c=Ausfahren; Zahl = Minuten, "
              "mit s = Sekunden (r20s); @von-bis in %; 4x(…) = Wiederholung.",
              "- % bedeutet: Rad % FTP, Laufen % der Schwellengeschwindigkeit, Schwimmen % der CSS-Geschwindigkeit "
              "(mehr % = schneller). Schwimmpausen ohne %.",
              f"- Zonen Rad: {_zones('ride')}",
              f"- Zonen Laufen: {_zones('run')}",
              f"- Zonen Schwimmen: {_zones('swim')}",
              f"- template + minutes statt steps: {', '.join(TEMPLATES)}"]
    return "\n".join(lines)
