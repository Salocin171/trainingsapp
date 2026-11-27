# Plan-Import: Format und KI-Auftrag

**„Plan importieren“** → JSON-Datei wählen oder einfügen → **Prüfen** (Vorschau pro Woche, Fehler mit genauer Stelle,
Warnung bei unbekannten Feldern) → **Importieren**. Optional ersetzt der Import geplante (nicht erledigte) Workouts im
Zeitraum, auch auf den Geräten. Neue Workouts werden wie beim normalen Speichern automatisch übertragen, wenn in den
Einstellungen „Automatisch senden“ aktiv ist. Ein vollständiges Beispiel liegt in
[`app/static/plan-example.json`](../app/static/plan-example.json) (Knopf „Beispiel einfügen“).

```json
{
  "name": "Aufbau 1 – Block 2",
  "start": "2026-12-21",
  "weeks": [
    { "week": 1, "days": {
      "tue": [
        { "sport": "ride", "name": "Schwelle 4x8", "time": "07:00",
          "steps": "w15@50-75, 4x(i8@97-102, r4@50-55), c10@50-65" },
        { "sport": "strength", "template": "stabi", "minutes": 40 } ],
      "sat": [ { "sport": "ride", "template": "long", "minutes": 210 } ]
    } }
  ]
}
```

| Feld | Bedeutung |
|---|---|
| `start` | Montag der 1. Woche (optional, sonst nächster Montag; im Dialog änderbar) |
| `weeks[].week` | Wochennummer ab 1 |
| `weeks[].days` | `mon`…`sun` (auch `Mo`…`So`, `Montag`…), Wert = Liste von Workouts |
| `workouts[]` | alternativ Workouts mit festem `date` (JJJJ-MM-TT) |
| `sport` | `swim`, `ride`, `run`, `strength` (Stabi), `mobility` (Dehnen/Yoga), `other` |
| `target` | `power` (% FTP), `pace` (% Schwellentempo bzw. CSS), `hr` (% LTHR) – Standard je Sport; gilt für alle Schritte ohne eigenes Ziel |
| `template` + `minutes` | Vorlage statt Schritten: `recovery`, `endurance`, `long`, `race_pace`, `tempo`, `sweetspot`, `threshold`, `vo2max`, `openers`, `brick`, `stabi`, `mobility` |
| `name`, `description` | Name und Beschreibung (optional) |
| `time` | Startzeit, z. B. `"07:00"` – steht dann vorne im Namen; daraus berechnet die Ernährung den Zeitpunkt |
| `steps` (Kurzform) | `"w15@50-75, 4x(i8@97-102, r4@50-55), c10@50-65"` – `w` Einwärmen, `i` Intervall, `r` Erholung, `s` Konstant, `c` Ausfahren; Zahl = Minuten, `s` dahinter = Sekunden (`r20s`); `@von-bis` in %; `4x(…)` = Wiederholung; `hr` / `pace` / `power` hinter den % gibt dem Schritt ein eigenes Ziel (`w15@70-80hr` = Einwärmen nach Puls). Spart gut 80 % Text gegenüber der Liste |
| `steps[]` (Liste) | `kind` (`warmup`, `interval`, `recovery`, `steady`, `cooldown`), `minutes` oder `seconds`, `low`/`high` in %, optional `target` |
| Wiederholung | `{ "repeat": 4, "steps": [ … ] }` |
| `fueling` | optional: `{ "before": "…", "during": "90 g/h", "after": "…", "day": "6–10 g/kg" }` → KH-Block in der Beschreibung. **Weglassen** = die App berechnet Kohlenhydrate, Trinken und Eiweiß selbst |
| `circuit` | Kraft/Stabi, Zirkel-Timer: `{ "work": 40, "rest": 20, "rounds": 3, "round_rest": 60, "exercises": ["Plank", { "name": "Split Squat", "reps": 8 }, { "name": "Wandsitz", "seconds": 45 }] }` (Sekunden, `rounds` 1–60; `reps` 0 = ohne feste Zahl; auch als Text `"Rudern \| 12 Wdh"`) |

## Plan von einer beliebigen KI schreiben lassen

Auch ohne Claude-Abo, z. B. mit ChatGPT oder Gemini: Im Import-Dialog **„KI-Auftrag kopieren“** → in die KI einfügen →
Antwort zurück in das JSON-Feld einfügen (Text und ```` ```json ````-Rahmen drumherum stören nicht) → Prüfen →
Importieren.

Der Auftrag (ca. 700–900 Tokens) enthält, was Claude per MCP sonst selbst nachschlägt: Gewicht, Schwellen, Saisonziel,
Fitness, Soll-Stunden und Blockfokus je Woche inkl. Entlastung und Hitzeeinheiten, Wochenmuster, Wettkämpfe, Zonen und
das Kurzformat ([`app/plan_prompt.py`](../app/plan_prompt.py), API: `GET /api/plan/prompt?weeks=4`). Ernährung muss die
KI nicht schreiben – die rechnet die App für jede Einheit selbst.

## Freie Zeiten statt festem Wochenmuster

Ein Wochenmuster ist optional. Im Feld *„Wann kannst du (nicht)?“* (Import-Dialog, Einrichtung, Einstellungen) stehen
feste Zeiten und Wünsche, z. B. „Mo–Fr erst ab 17 Uhr · Schwimmbad nur Di und Do früh“ – der Text wird gemerkt.

Zusätzlich lassen sich Kalender als **iCal-Link** hinterlegen (iCloud: Kalender-App → Rechtsklick auf den Kalender →
Kalender teilen → *Öffentlicher Kalender* → Link kopieren; Outlook: Kalender veröffentlichen → ICS-Link). Den eigenen
Trainingskalender nicht eintragen, sonst blockieren die Trainings selbst die Zeiten. Die App liest daraus die belegten
Zeiten des Blocks (inkl. Wiederholungen und Ausnahmen) und schreibt **nur die Uhrzeiten** in den Auftrag, keine
Termintitel; der Link bleibt in der lokalen Datenbank ([`app/availability.py`](../app/availability.py)).

Ohne eigenes Wochenmuster bekommt die KI Regeln zur Verteilung (Häufigkeit je Sport, Abstand harter Einheiten,
Ruhetag) und legt jede Einheit mit `time` in ein freies Zeitfenster. Ein vom Standard abweichendes Wochenmuster wird als
Orientierung mitgeschickt.
