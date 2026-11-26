# Trainingsapp

Eigene Trainingsplanung für den Mac – ausgelegt auf Triathlon/Ironman: Kalender mit mehreren
Einheiten pro Tag, Workout-Editor (Schwimmen, Rad, Laufen, Stabi, Dehnen/Yoga), Periodisierung
bis zum Wettkampf, Wochenstunden, Ernährung vor/während/nach jeder Einheit, eigene Ziele und
Übertragung auf **Garmin**, **Wahoo** (über intervals.icu) und **Zwift**.

Läuft lokal auf deinem Mac (Python-Server + Browser-Oberfläche). Nur für macOS.

## Installation (einmalig, ca. 10 Minuten)

1. **Herunterladen:** Programm *Terminal* öffnen (Spotlight: ⌘ + Leertaste → „Terminal“), diese Zeile einfügen, Enter:

   ```bash
   git clone https://github.com/Salocin171/trainingsapp.git ~/Trainingsapp && open ~/Trainingsapp
   ```

   Fragt macOS nach den **Entwicklertools**: „Installieren“ klicken, warten, dann die Zeile noch einmal ausführen.
2. **Starten:** Im geöffneten Ordner **`Trainingsapp.command` doppelklicken.** Beim ersten Mal wird alles eingerichtet.
   Fehlt ein aktuelles Python (macOS bringt nur 3.9 mit, gebraucht wird 3.12+), öffnet sich python.org:
   „macOS 64-bit universal2 installer“ laden, die `.pkg` durchklicken, dann erneut doppelklicken.
3. **Einrichten:** Im Browser öffnet sich der Dialog **„Willkommen“**: Garmin verbinden (optional, holt deine
   Schwellenwerte und das letzte Trainingsjahr), Gewicht und Schwellen prüfen, Saisonziel eintragen – fertig.
   Später erneut über **Einstellungen → Einrichtung / Garmin verbinden …**
4. Optional **`autostart.command`** doppelklicken: Die App läuft dann immer im Hintergrund (siehe unten).

**Updates:** Gibt es eine neue Version, erscheint oben in der App der Button **„⬆ Update“** (die App schaut alle 30 Minuten nach) – ein Klick holt sie, die Seite lädt danach neu. Alternativ **`Update.command`** doppelklicken; bei einer als ZIP geladenen App einmal nötig, danach geht es per Button.

**Deine Daten** gehören nur dir und bleiben auf deinem Mac: Trainingsdaten und Einstellungen in `data/training.db`,
Anmeldungen (Garmin) in `~/.trainingsapp/`. Beides ist nicht im Git – Updates überschreiben es nicht, und
niemand sonst sieht es. **Sichern:** `data/training.db` kopieren (z. B. in die iCloud). Ein zweites Profil auf
demselben Mac (z. B. zum Ausprobieren): `TRAININGSAPP_DATA_DIR=~/Trainingsapp-Test ./Trainingsapp.command`.

> Die Garmin-Anbindung nutzt eine inoffizielle Bibliothek; Garmin kann sie jederzeit sperren. Die Ernährungswerte
> sind Richtwerte und keine medizinische Beratung.

## Starten

**Doppelklick auf `Trainingsapp.command`** im Finder. Beim ersten Start wird die
Python-Umgebung eingerichtet, danach öffnet sich der Browser auf http://127.0.0.1:8765.

> Falls macOS den Start blockiert: Rechtsklick → Öffnen (einmalig).
> Tipp: Im Browser (Safari: Ablage → „Zum Dock hinzufügen“) wird daraus eine eigene App im Dock.

**Im Hintergrund (empfohlen, v. a. für Claude):** Doppelklick auf `autostart.command` richtet einen
LaunchAgent ein – die App startet dann beim Anmelden ohne Terminalfenster und nach einem Absturz neu.
`Trainingsapp.command` öffnet danach nur noch den Browser (und installiert neue Pakete).
Log: `~/Library/Logs/trainingsapp.log`. Entfernen: `./autostart.command off`.
Neustart von Hand: `launchctl kickstart -k gui/$(id -u)/de.trainingsapp`.

> Beim ersten Zwift-Export fragt macOS evtl., ob „python3“ auf den Ordner *Dokumente* zugreifen darf → Erlauben.

Für die Entwicklung in VS Code:

```bash
code .
```

Dann **F5** → „Trainingsapp (Server mit Reload)“. Änderungen an Python-Dateien laden
den Server neu, Änderungen in `app/static/` brauchen nur einen Browser-Reload.

## Geräte verbinden

| Gerät | Weg | Einrichtung |
|---|---|---|
| **Garmin** (Uhr / Edge) | Workout wird in Garmin Connect hochgeladen und im Garmin-Kalender eingeplant. Das Gerät lädt es beim nächsten Sync. | Im Einrichtungsdialog (**Einstellungen → Einrichtung / Garmin verbinden …**) – oder im Terminal: `.venv/bin/python -m app.garmin_login` |
| **Wahoo** (z. B. Bolt) | Über [intervals.icu](https://intervals.icu) (kostenlos). intervals.icu schickt geplante Workouts an Wahoo, das Gerät lädt sie beim Sync. | 1. intervals.icu-Konto anlegen, unter *Settings → Connections* Wahoo verbinden und „Upload planned workouts“ aktivieren. 2. API-Key + Athleten-ID (*Settings → Developer Settings*) in `.env` eintragen (Vorlage: `.env.example`). |
| **Zwift** | `.zwo`-Datei im Zwift-Ordner `~/Documents/Zwift/Workouts/<ID>/`. Erscheint in Zwift unter *Custom Workouts* (Datum steht vorne im Namen). | Nichts – der Ordner wird automatisch gefunden. |

### Kalender (iCloud, Outlook & Co. – über die Kalender-App des Macs)

Geplante Workouts landen als ganztägige Termine in einem Kalender deiner Wahl – Titel „Sportart – Programm“
(z. B. „Laufen – Locker 40“, lange Programmnamen nur in der Beschreibung), Beschreibung mit allen Schritten in
Watt / Pace / Puls, Dauer und TSS. Verschieben, Ändern und Löschen in der App wird übernommen.

Die App schreibt in die **Kalender-App des Macs**; liegt der gewählte Kalender bei iCloud oder einem anderen Konto
(*Systemeinstellungen → Internetaccounts*), synchronisiert macOS ihn selbst dorthin und aufs iPhone. Keine
Cloud-Einrichtung nötig:

1. **Einstellungen → Automatisch senden → Kalender** anhaken und rechts den Kalender wählen (z. B. „Sport“ in iCloud;
   am besten ein eigener Kalender nur für Trainings).
2. Beim ersten Mal fragt macOS: **„… möchte „Kalender“ steuern“ → OK.** Verpasst? *Systemeinstellungen → Datenschutz &
   Sicherheit → Automation* → beim Programm (Terminal bzw. „Python“ beim Autostart) **Kalender** einschalten.
3. Einmal **„Geplante Workouts jetzt eintragen / aktualisieren“** für die bereits geplanten Workouts (trägt Fehlendes nach und korrigiert vorhandene Termine).

Termine erscheinen auf anderen Geräten, sobald der Mac sie synchronisiert hat (er muss dafür an sein).

Warum nicht direkt zu Wahoo? Die Wahoo-Cloud-API braucht einen freigeschalteten
Entwickler-Account. intervals.icu ist offiziell angebunden und liefert zusätzlich
Aktivitäten mit Trainingslast für die Empfehlungen.

Die Garmin-Anbindung nutzt die inoffizielle Bibliothek
[`garminconnect`](https://github.com/cyberjunky/python-garminconnect). Garmin kann
deren Login jederzeit ändern – dann hilft meist `pip install -U garminconnect`.

## Benutzung

- **Klick auf ein geplantes Workout** → Details: Beschreibung, Uhrzeit (aus dem Namen, z. B. „08:00 · …“), Dauer,
  TSS, IF, Profil, Ablauf mit Watt/Pace und **Ernährung vor · während · nach** der Einheit (Kohlenhydrate,
  Flüssigkeit, Eiweiß, Zeitpunkt, Tagesziel). Gerechnet mit Gewicht und Schweißrate aus den Einstellungen, Art der
  Einheit, Wochen bis zum Wettkampf (Darmtraining) und den anderen Einheiten am Tag (Koppellauf, Qualität in < 8 h
  → schnell auffüllen). Steht in der Beschreibung ein Block „KH (… kg): – Vorher: … – Während: … – Danach: …“, gelten
  dessen Zahlen. Von dort aus: **Bearbeiten**, **Als erledigt markieren**, bei Kraft/Stabi **▶ Workout starten**
  (Zirkel-Timer). Regeln in `app/nutrition.py`.
- **Klick auf einen Tag** → neues Workout. Vorlage wählen (Grundlage, Sweet Spot,
  Schwelle, VO2max …), Schritte anpassen, Vorschau + TSS sehen.
- **Zirkel-Timer** für Kraft/Stabi: im Workout **„▶ Zirkel-Timer“** (oder oben **„⏱ Timer“** ohne Workout).
  Belastung und Pause in Sekunden, Runden (max. 60, eine Runde = jede Übung einmal), Pause nach jeder Runde,
  Übungen (eine pro Zeile). Beim Stabi-Workout werden Übungen und 40/20 aus der Beschreibung übernommen.
  Hinten an der Übung `| 12 Wdh` = Wiederholungen: statt Countdown steht „12 Wdh“ da, weiter mit **„✓ Fertig“**
  (Leertaste/Enter); `| Wdh` ohne Zahl z. B. für „bis kurz vor Versagen“; `| 45 s` = eigene Dauer.
  Während des Laufs: aktuelle und nächste Übung groß, Farbe je Phase, Piepton bei 3-2-1, Ansage der Übung,
  Bildschirm bleibt an. Tasten: Leertaste = Pause, ← / → = zurück / überspringen. Am Ende
  „Als erledigt speichern“ – die Timer-Einstellungen bleiben am Workout gespeichert.
  An Garmin geht derselbe Zirkel (Wiederholungen als Wdh-Ziel, ohne Zahl per Runden-Taste): je Übung ein Schritt (mit Garmin-Übung aus dem Katalog, Liste
  `EXERCISES` in `app/sync/garmin.py`, unbekannte nur als Notiz), Pausen, Rundenpause, Runden als Wiederholung.
- **„Speichern & senden“** überträgt an die angehakten Geräte. Einmal übertragene
  Workouts werden bei jeder Änderung (auch Verschieben per Drag & Drop) aktualisiert,
  beim Löschen auch dort entfernt.
- **Beim Öffnen** holt die App automatisch FTP, LTHR (Rad und Laufen getrennt), Max-Puls und
  Schwellentempo von Garmin (abschaltbar) sowie die Aktivitäten der letzten 14 Tage.
- **„Aktivitäten importieren“** holt die letzten 365 Tage (Garmin und/oder intervals.icu)
  plus Garmin-Trainingsbereitschaft/HRV des Tages.
- **Seitenleiste**: aktueller Block mit Zeitleiste bis zum Wettkampf, Position im
  Belastungszyklus (B1 B2 B3 E), Wochenstunden Soll/Ist/geplant, Ziele, Form, Vorschläge.
- **Ziele** („+ Ziel“): Stunden oder Kilometer, pro Sport oder gesamt, pro Woche/Monat/Jahr
  oder eigener Zeitraum. Die Markierung im Balken zeigt, wo du bei gleichmäßigem Training
  heute stehen müsstest.
- **Einstellungen**: Schwellen (FTP, LTHR Rad/Laufen, Schwellentempo, CSS), Wettkampf + Art,
  Wochenstunden, Entlastungsrhythmus, Wochenmuster mit beliebig vielen Einheiten pro Tag.

## Auswertung

- **Compliance im Kalender** (wie TrainingPeaks): farbiger Streifen links an geplanten Workouts –
  grün 80–120 % des Plans, gelb 50–79 % / 121–150 %, orange darüber/darunter, rot = verpasst.
  Verglichen wird nach Dauer. Ungeplante Aktivitäten sind gestrichelt.
- **Training erkennen**: Eine importierte Aktivität wird dem geplanten Workout desselben Tags und Sports zugeordnet, im
  Kalender steht dann nur noch eine Karte. Dafür muss es grob passen: gleicher Name, oder Dauer ungefähr gleich (60–160 %,
  Schwimmen 50–200 %, Stabi/Dehnen 40–200 %) und die Härte grob stimmt (Pulszonen, Leistung). Sonst
  bleiben beide stehen und das Workout zeigt „≠ anders als geplant“, z. B. 30 min locker statt 5×1000 m.
  Liegt die Erkennung daneben: Klick auf die Aktivität → **Geplantes Workout** von Hand wählen (`app/compliance.py`).
- **Feedback**: Klick auf eine erledigte Aktivität → Kennzahlen, Pulszonen, RPE (0–10), Befinden (1–5), Notiz.
  Regeln in `app/feedback.py`: lockere Einheit mit RPE ≥ 8 → 2 Tage nichts Hartes; Ø-RPE ≥ 7 bei
  Ermüdung → 2 Tage reduziert; harte Einheiten mit RPE ≤ 3 → Hinweis, die Schwellen zu testen.
- **Analyse** (Knopf oben):
  - *Kennzahlen* von Garmin: Trainingsstatus, VO2max, Endurance Score, Hitzeanpassung,
    Renn-Prognosen, FTP-/VO2max-Verlauf (6 h zwischengespeichert, „↻ Garmin“ lädt neu).
  - *Leistungskurve* 90 vs. 365 Tage mit FTP-Schätzungen (95 % von 20 min, Critical Power, 60 min).
  - *Effizienz*: Efficiency Factor (NP bzw. Tempo pro Herzschlag) lockerer Einheiten mit 28-Tage-Trend.
  - *Zonen*: Zeit in Pulszonen pro Woche und Anteil locker (Basis auch für den 80/20-Hinweis).
  - *Renntag*: Zielwerte, Zeiten und Verpflegung je Disziplin (Annahmen in `RACE_DEFAULTS`, `app.js`).
- **Saisonplanung**: Ziel-CTL vor dem Tapering (Einstellungen) → nötiger Anstieg pro Woche, Risiko
  (Rampen-Tabelle in `periodization.RAMP_RISK`) und nötige Wochen-TSS/-Stunden in der Blockkarte.
  Weitere Wettkämpfe als **B** (Mini-Taper + volle Erholung) oder **C** (durchtrainiert, Erholung ×0,6).
  Taper, Erholung und Laufpause hängen von der Distanz ab (`app/races.py`), z. B.:

  | Distanz (B) | Mini-Taper | Erholung (davon nur Regeneration) | Laufpause |
  |---|---|---|---|
  | Lauf 5 km / 10 km | 2 / 3 Tage | 2 / 3 (0 / 1) Tage | – |
  | Halbmarathon | 4 Tage | 7 (1) Tage | 2 Tage |
  | Marathon | 7 Tage | 14 (3) Tage | 5 Tage |
  | Ultralauf | 7 Tage | 21 (4) Tage | 7 Tage |
  | Triathlon Sprint / Olympisch | 2 / 3 Tage | 2 / 4 (0 / 1) Tage | – / 1 Tag |
  | 70.3 / Ironman | 4 / 10 Tage | 7 / 21 (2 / 4) Tage | 3 / 7 Tage |

  In der Laufpause schlägt die App lockeres Rad statt Laufen vor; nach der Regenerationsphase steigt der
  Umfang von 70 % auf 90 %, harte Einheiten erst nach Ende der Erholung.
- **Konflikte mit Wettkämpfen** (`app/conflicts.py`): Geplante oder importierte Workouts werden nie automatisch
  geändert. Passt eines nicht zu Taper, Renntag, Regeneration, Erholung oder Laufpause eines Wettkampfs
  (auch des A-Rennens, dort nur die letzten 3 Tage und danach), ist es im Kalender mit ⚠ markiert und erscheint
  in der Seitenleiste mit konkretem Vorschlag („Schwelle → Grundlage 60 min“, „Laufen → Rad locker“,
  „entfernen“). „Anpassen“ übernimmt ihn – auch auf den Geräten, falls das Workout übertragen wurde.
- **CSS**: Eine *neue* CSS-Messung von Garmin wird übernommen, dein eigener Wert sonst nicht überschrieben.

Alle Analysen nutzen die Garmin-Zusammenfassungen der Aktivitäten (Puls, NP, Zonen, Bestleistungen) –
Sekundendaten werden (noch) nicht geladen.

## Plan-Import (z. B. 4-Wochen-Block)

**„Plan importieren“** → JSON-Datei wählen oder einfügen → **Prüfen** (Vorschau pro Woche, Fehler mit
genauer Stelle, Warnung bei unbekannten Feldern) → **Importieren**. Optional ersetzt der Import geplante (nicht erledigte) Workouts im
Zeitraum – auch auf den Geräten. Neue Workouts werden wie beim normalen Speichern automatisch übertragen,
wenn in den Einstellungen „Automatisch senden“ aktiv ist. Ein vollständiges Beispiel liegt in
`app/static/plan-example.json` (Knopf „Beispiel einfügen“).

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
| `steps` (Kurzform) | `"w15@50-75, 4x(i8@97-102, r4@50-55), c10@50-65"` – `w` Einwärmen, `i` Intervall, `r` Erholung, `s` Konstant, `c` Ausfahren; Zahl = Minuten, `s` dahinter = Sekunden (`r20s`); `@von-bis` in %; `4x(…)` = Wiederholung; `hr` / `pace` / `power` hinter den % gibt dem Schritt ein eigenes Ziel (`w15@70-80hr` = Einwärmen nach Puls, auch wenn die Intervalle nach Pace laufen). Spart gut 80 % Text gegenüber der Liste |
| `steps[]` (Liste) | `kind` (`warmup`, `interval`, `recovery`, `steady`, `cooldown`), `minutes` oder `seconds`, `low`/`high` in %, optional `target` (eigenes Ziel des Schritts) |
| Wiederholung | `{ "repeat": 4, "steps": [ … ] }` |
| `fueling` | optional: `{ "before": "…", "during": "90 g/h", "after": "…", "day": "6–10 g/kg" }` → KH-Block in der Beschreibung. **Weglassen** = die App berechnet Kohlenhydrate, Trinken und Eiweiß selbst |
| `circuit` | Kraft/Stabi, Zirkel-Timer: `{ "work": 40, "rest": 20, "rounds": 3, "round_rest": 60, "exercises": ["Plank", { "name": "Split Squat", "reps": 8 }, { "name": "Wandsitz", "seconds": 45 }] }` (Sekunden, `rounds` 1–60; `reps` 0 = ohne feste Zahl; auch als Text `"Rudern \| 12 Wdh"`) |

**Plan von einer beliebigen KI schreiben lassen** (auch ohne Claude-Abo, z. B. ChatGPT oder Gemini):
Im Import-Dialog **„KI-Auftrag kopieren“** → in die KI einfügen → Antwort zurück in das JSON-Feld einfügen
(Text und ```` ```json ````-Rahmen drumherum stören nicht) → Prüfen → Importieren. Der Auftrag (ca. 700–900 Tokens)
enthält, was Claude per MCP sonst selbst nachschlägt: Gewicht, Schwellen, Saisonziel, Fitness, Soll-Stunden und
Blockfokus je Woche inkl. Entlastung und Hitzeeinheiten, Wochenmuster, Wettkämpfe, Zonen und das Kurzformat
(`app/plan_prompt.py`, API: `GET /api/plan/prompt?weeks=4`). Ernährung muss die KI nicht schreiben – die rechnet die
App für jede Einheit selbst.

**Freie Zeiten statt festem Wochenmuster:** Ein Wochenmuster ist optional. Im Feld *„Wann kannst du (nicht)?“*
(Import-Dialog, Einrichtung, Einstellungen) stehen feste Zeiten und Wünsche, z. B. „Mo–Fr erst ab 17 Uhr · Schwimmbad
nur Di und Do früh“ – der Text wird gemerkt. Zusätzlich lassen sich Kalender als **iCal-Link** hinterlegen (iCloud: Kalender-App → Rechtsklick auf den Kalender →
Kalender teilen → *Öffentlicher Kalender* → Link kopieren; Outlook: Kalender veröffentlichen → ICS-Link; den eigenen
Trainingskalender nicht eintragen, sonst blockieren die Trainings selbst die Zeiten). Die App liest daraus die belegten Zeiten des Blocks
(inkl. Wiederholungen und Ausnahmen) und schreibt **nur die Uhrzeiten** in den Auftrag, keine Termintitel; der Link
bleibt in der lokalen Datenbank (`app/availability.py`). Ohne eigenes Wochenmuster bekommt die KI Regeln zur
Verteilung (Häufigkeit je Sport, Abstand harter Einheiten, Ruhetag) und legt jede Einheit mit `time` in ein freies
Zeitfenster. Ein vom Standard abweichendes Wochenmuster wird als Orientierung mitgeschickt.

## Claude-Zugriff per MCP

`app/mcp_server.py` stellt die App als MCP-Server bereit, damit Claude sie direkt bedienen kann
(„Was steht diese Woche an?“, „Plane mir Dienstag 75 min Sweet Spot und schick es an Garmin“).
Der Server spricht mit der **laufenden** App über ihre API – die App muss also gestartet sein
(am einfachsten dauerhaft per `autostart.command`, siehe „Starten“).

| Tool | Zweck |
|---|---|
| `get_status` | Block, Belastungs-/Entlastungswoche, CTL/ATL/TSB, Ziel-CTL, Warnungen, Wochenstunden |
| `get_calendar`, `get_workout` | Workouts (mit Compliance/Feedback), Aktivitäten (Puls, NP, Zonen), Wettkämpfe |
| `get_recommendations`, `accept_suggestion` | Vorschläge der nächsten 7 Tage, übernehmen |
| `create_workout`, `update_workout`, `delete_workout` | Workouts bearbeiten (auch Zirkel-Timer: `circuit`), optional an Geräte senden (`send_to`) |
| `get_plan_brief` | Kompakter Auftrag für einen Block: Schwellen, Soll-Stunden je Woche, Wochenmuster, Wettkämpfe, Format |
| `import_plan` | JSON-Plan prüfen (gibt `preview_id` zurück) bzw. mit `preview_id` importieren |
| `get_analysis` | Garmin-Kennzahlen, Leistungskurve, Efficiency Factor, Zonen |
| `set_activity_feedback` | RPE / Befinden / Notiz zu einer Aktivität |
| `get_settings`, `update_settings`, `add_race`, `delete_race` | Schwellen, Wettkämpfe, Wochenstunden |
| `send_planned_workouts` | Alle geplanten Workouts an Garmin / Wahoo / Zwift / Kalender senden |
| `check_race_conflicts`, `resolve_race_conflicts` | Workouts, die nicht zu Wettkämpfen passen – prüfen / Vorschläge übernehmen |
| `import_activities` | Aktivitäten von Garmin nachladen |

**Claude Code** (einmalig, im Ordner der App ausführen; gilt dann für alle Sitzungen):

```bash
cd ~/Trainingsapp
claude mcp add trainingsapp --scope user -- "$PWD/.venv/bin/python" "$PWD/app/mcp_server.py"
claude mcp list        # → trainingsapp … ✔ Connected
```

**Claude Desktop**: In *Einstellungen → Entwickler → Konfiguration bearbeiten*
(`~/Library/Application Support/Claude/claude_desktop_config.json`) eintragen und Claude Desktop neu starten:

```json
{ "mcpServers": { "trainingsapp": {
    "command": "/Users/DEIN-BENUTZERNAME/Trainingsapp/.venv/bin/python",
    "args": ["/Users/DEIN-BENUTZERNAME/Trainingsapp/app/mcp_server.py"] } } }
```

**Tokens sparen beim Block planen:** `get_plan_brief` liefert alle Vorgaben in einem kompakten Text (statt
`get_status` + `get_settings` + `get_calendar`). Schritte in der Kurzform schreiben. `import_plan` prüft und gibt eine
`preview_id` zurück; danach nur `import_plan(preview_id=…)` – der Plan wird nicht ein zweites Mal gesendet.

Neues Tool → Funktion mit `@server.tool(...)` in `app/mcp_server.py`, Docstring = Beschreibung für Claude.
Erwartbare Fehler als `ToolError` werfen, sonst sieht Claude nur „Error executing tool“.

## Wie die Empfehlungen funktionieren

Bewusst regelbasiert und nachvollziehbar, jeder Vorschlag hat eine Begründung.

1. **Periodisierung** (`app/periodization.py`), rückwärts vom Wettkampf gezählt. Für einen Ironman:
   Grundlage → Aufbau 1 (8 Wo) → Aufbau 2 (8 Wo) → Wettkampfspezifisch (8 Wo) → Tapering (3 Wo inkl.
   Rennwoche) → 2 Wochen Regeneration. Für 70.3 und andere Wettkämpfe gibt es kürzere Pläne.
   - **Belastung/Entlastung**: z. B. 3 Wochen steigend (90 % → 100 % → 110 %), dann 1 Woche Entlastung
     (60 %). Der Rhythmus ist am Wettkampf ausgerichtet: Die letzte Woche vor dem Tapering ist die härteste.
     Mit **Zyklusstart** (Einstellungen) zählt der Rhythmus stattdessen ab einem festen Montag vorwärts –
     passend zu einem eigenen Saisonplan; Wochen davor gelten als Vorlauf. Fiele die Entlastung direkt vor das
     Tapering, bleibt diese Woche Belastung. **Taper-Wochen** überschreibt
     die Taper-Länge (z. B. 2 statt 3 beim Ironman).
   - **Wochenstunden** (Schwimmen + Rad + Laufen) = eingestellte Stunden × Blockfaktor × Wochenfaktor.
     Stabi und Dehnen kommen obendrauf.
   - **Hitzetraining** ab ca. 6 Wochen vor dem Renntag: 3–4 lockere Rad-/Laufeinheiten pro Woche
     werden als Hitzeeinheit markiert (Indoor ohne Ventilator oder Sauna danach), in der Woche vor
     dem Rennen nur noch 2, in der Rennwoche keine.
2. **Wochenmuster**: pro Tag beliebig viele Einheiten (Sport + Typ). Geplante Workouts und heute
   erledigte Aktivitäten belegen passende Einheiten, die freien bekommen Vorschläge. Die Wochenstunden
   werden nach Gewicht (Typ × Sport, z. B. langes Rad = großer Anteil) verteilt. Verpasste Einheiten
   werden nicht auf die restlichen Tage gepackt.
3. **Harte Einheiten** rotieren je Block (Grundlage: Sweet Spot/Tempo, Aufbau: Schwelle/VO2max,
   Wettkampfspezifisch: Wettkampftempo/Schwelle). Lange Einheiten werden im wettkampfspezifischen Block
   abwechselnd zu Wettkampftempo-Einheiten.
4. **Regeln** (Tag für Tag mit simulierter Belastung):
   - keine harte Einheit in derselben Sportart am Vor- oder Folgetag einer harten Einheit
   - höchstens eine harte Rad-/Laufeinheit pro Tag (Schwimmen zählt nicht mit)
   - Entlastungswoche: Intensität raus
   - keine Intensität bei TSB < −25, nur Regeneration bei TSB < −35
   - heute lockerer, wenn Garmin niedrige Trainingsbereitschaft oder schlechte HRV meldet
   - Koppellauf nach dem langen Rad in Aufbau 2, im wettkampfspezifischen Block und im Tapering
   - Verpflegungshinweis (60–90 g KH/h) bei langen Einheiten ab Aufbau 2
   - Rennwoche: kein Stabi in den letzten 10 Tagen, Aktivierung 3 Tage und 1 Tag vorher, Ruhetag 2 Tage vorher
5. **Warnungen**: zu schnelle Rampe (> 8 CTL/Woche), kein Ruhetag in 7 Tagen,
   mehr als 25 % intensive Ausdauerzeit (80/20).

Bereits geplante Workouts werden nie überschrieben, sondern fließen in die Simulation ein.

**Anpassen**: Blocklängen in `RACE_PLANS`, Umfang in `BLOCK_VOLUME`/`TAPER_VOLUME`, Hitzetraining in
`HEAT_SESSIONS` (alle in `periodization.py`); Gewichte, Rotation und Regeln in `recommend.py`;
Zonen und Intervalle je Sport in `templates.py`.

## Projektstruktur

```
app/
  main.py          API-Endpunkte (FastAPI)
  db.py            SQLite + Standard-Einstellungen
  workouts.py      Workout-Format, Dauer, TSS
  templates.py     Workout-Vorlagen (eigene hier ergänzen)
  load.py          CTL / ATL / TSB
  periodization.py Blöcke, Belastungs-/Entlastungswochen, Wochenstunden, Hitzetraining
  recommend.py     Empfehlungslogik
  volume.py        Wochenstunden-Übersicht und Ziele (Stunden/Kilometer)
  plan_import.py   JSON-Trainingsplan prüfen und in Workouts umwandeln
  compliance.py    Plan vs. Ist (Farben im Kalender)
  feedback.py      RPE/Befinden auswerten (Regeln für die Vorschläge)
  analysis.py      Efficiency Factor, Zonen pro Woche, Leistungskurve
  nutrition.py     Verpflegung vor/während/nach einer Einheit (KH, Trinken, Protein)
  plan_prompt.py   KI-Auftrag für einen Trainingsblock (auch für Claude: get_plan_brief)
  availability.py  belegte Zeiten aus iCal-Links (nur Uhrzeiten)
scripts/ensure_venv.sh  Python ab 3.12 finden, .venv anlegen, Pakete installieren (für die .command-Dateien)
  races.py         Wettkampfdistanzen: Mini-Taper, Erholung, Laufpause
  conflicts.py     Geplante Workouts vs. Wettkämpfe (mit Änderungsvorschlag)
  mcp_server.py    MCP-Server für Claude (Tools über die API der laufenden App)
  sync/            garmin.py, intervals.py, zwift.py, maccal.py (Kalender-App) – je push() / remove()
  garmin_login.py  einmalige Garmin-Anmeldung
  static/          Oberfläche (index.html, app.js, styles.css, FullCalendar)
tests/             pytest: .venv/bin/python -m pytest
```

**Erweitern:**
- Neue Vorlage → Funktion in `templates.py` + Eintrag in `TEMPLATES`.
- Neues Ziel (z. B. TrainingPeaks) → Modul in `app/sync/` mit `push()`/`remove()` und in
  `app/sync/__init__.py` eintragen.
- Neue Regel → in `recommend.plan_days()` bzw. `analyze()`, Test in `tests/test_core.py`.
