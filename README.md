# Trainingsapp

Trainingsplanung für Triathlon und Ironman, lokal auf dem Mac: Kalender mit mehreren Einheiten pro Tag,
Workout-Editor, Periodisierung bis zum Wettkampf, Vorschläge mit Begründung, Ernährung je Einheit, Auswertung – und
Übertragung auf **Garmin**, **Wahoo** (über intervals.icu), **Zwift** und die **Kalender-App**. Claude kann die App per
MCP bedienen.

Nur für macOS. Läuft als kleiner Python-Server, bedient wird sie im Browser.

## Installation (einmalig, ca. 10 Minuten)

1. **Herunterladen:** *Terminal* öffnen (⌘ + Leertaste → „Terminal“), einfügen, Enter:

   ```bash
   git clone https://github.com/Salocin171/trainingsapp.git ~/Trainingsapp && open ~/Trainingsapp
   ```

   Fragt macOS nach den **Entwicklertools**: „Installieren“, warten, die Zeile noch einmal ausführen.
2. **Starten:** **`Trainingsapp.command` doppelklicken.** Beim ersten Mal wird alles eingerichtet. Fehlt Python 3.12+,
   öffnet sich python.org: „macOS 64-bit universal2 installer“ laden, installieren, erneut doppelklicken.
   (Blockiert macOS den Start: Rechtsklick → Öffnen.)
3. **Einrichten:** Im Browser öffnet sich **„Willkommen“**: Garmin verbinden (optional, holt Schwellenwerte und das
   letzte Trainingsjahr), Gewicht und Schwellen prüfen, Saisonziel eintragen. Später: *Einstellungen → Einrichtung*.
   Tipp: In Safari *Ablage → Zum Dock hinzufügen* – dann ist die App ein eigenes Programm im Dock.
4. **Autostart** (empfohlen, v. a. für Claude): in der Einrichtung **„Autostart einrichten“**. Die App läuft dann
   im Hintergrund und startet beim Anmelden. Log: `~/Library/Logs/trainingsapp.log`, entfernen: `./autostart.command off`.

**Updates:** Gibt es eine neue Version, erscheint oben **„⬆ Update“** – ein Klick genügt. Bei einer als ZIP geladenen
App einmal `Update.command` doppelklicken.

**Deine Daten** bleiben auf deinem Mac und sind nicht im Git: Trainingsdaten in `data/training.db` (zum Sichern
kopieren), Garmin-Anmeldung in `~/.trainingsapp/`. Zweites Profil zum Ausprobieren:
`TRAININGSAPP_DATA_DIR=~/Trainingsapp-Test ./Trainingsapp.command`.

> Die Garmin-Anbindung nutzt die inoffizielle Bibliothek [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
> und kann jederzeit brechen (dann meist `pip install -U garminconnect`). Ernährungswerte sind Richtwerte, keine
> medizinische Beratung.

## Geräte verbinden

| Ziel | Weg | Einrichtung |
|---|---|---|
| **Garmin** (Uhr / Edge) | Workout im Garmin-Connect-Kalender, das Gerät lädt es beim Sync | Einrichtungsdialog, oder `.venv/bin/python -m app.garmin_login` |
| **Wahoo** | über [intervals.icu](https://intervals.icu) (kostenlos) | intervals.icu: Wahoo verbinden, „Upload planned workouts“ an. API-Key + Athleten-ID in `.env` (Vorlage `.env.example`) |
| **Zwift** | `.zwo`-Datei, erscheint unter *Custom Workouts* | nichts – der Ordner wird gefunden (sonst in den Einstellungen setzen); macOS fragt evtl. nach Zugriff auf *Dokumente* → Erlauben |
| **Kalender** (iCloud, Outlook …) | ganztägige Termine über die Kalender-App des Macs | *Einstellungen → Automatisch senden → Kalender* und Kalender wählen; macOS-Abfrage „… möchte Kalender steuern“ mit OK bestätigen |

Einmal übertragene Workouts werden bei jeder Änderung aktualisiert und beim Löschen auch dort entfernt.

## Was die App kann

- **Kalender** mit Belastungsblöcken, Monats-, Block-, Wochen- und Listenansicht; Drag & Drop zum Verschieben.
- **Wochenübersicht** unter der Wochenansicht: km und Stunden je Sport, Soll, Intensität, harte Einheiten, Form am Sonntag.
- **Workout-Editor** mit Vorlagen, Wiederholungen und Zielen je Schritt (Watt, Pace, Puls); **Zirkel-Timer** für Stabi.
- **Periodisierung und Vorschläge**: Blöcke rückwärts vom Wettkampf, Belastungs-/Entlastungswochen, Soll-Stunden,
  Hitzetraining, Regeln für harte Einheiten, B-/C-Wettkämpfe mit Mini-Taper und Erholung.
- **Plan vs. Ist**: importierte Aktivitäten werden den Workouts zugeordnet (Compliance-Farben), RPE und Befinden fließen
  in die Vorschläge ein.
- **Abschnitte** jeder Einheit: Zwischenzeiten, Pace/Watt und Puls je Intervall, verglichen mit dem Ziel aus dem Plan.
- **Ernährung** vor, während und nach jeder Einheit; **Analyse** mit Garmin-Kennzahlen, Leistungskurve, Effizienz,
  Pulszonen und Renntag-Planung.
- **Plan-Import** als JSON, auch von einer beliebigen KI („KI-Auftrag kopieren“).

Details, Regeln und Formeln: [docs/funktionen.md](docs/funktionen.md) · Plan-Format: [docs/plan-format.md](docs/plan-format.md)

## Claude per MCP

[`app/mcp_server.py`](app/mcp_server.py) macht die App für Claude bedienbar („Was steht diese Woche an?“, „Plane mir
Dienstag 75 min Sweet Spot und schick es an Garmin“). Er spricht mit der **laufenden** App, also am besten mit Autostart.

**Claude Code** (einmalig, im Ordner der App):

```bash
claude mcp add trainingsapp --scope user -- "$PWD/.venv/bin/python" "$PWD/app/mcp_server.py"
```

**Claude Desktop**: *Einstellungen → Entwickler → Konfiguration bearbeiten*, eintragen, neu starten:

```json
{ "mcpServers": { "trainingsapp": {
    "command": "/Users/DEIN-BENUTZERNAME/Trainingsapp/.venv/bin/python",
    "args": ["/Users/DEIN-BENUTZERNAME/Trainingsapp/app/mcp_server.py"] } } }
```

Tools: Status, Kalender, Workouts anlegen/ändern/löschen und senden, Vorschläge, Plan-Brief und Plan-Import, Analyse,
Feedback, Einstellungen, Wettkämpfe und Konflikte, Aktivitäten importieren. Zum Block planen spart `get_plan_brief`
Tokens (alle Vorgaben in einem Text); `import_plan` prüft zuerst und importiert dann per `preview_id`.

## Entwicklung

In VS Code **F5** → „Trainingsapp (Server mit Reload)“. Python-Änderungen laden den Server neu, Änderungen in
`app/static/` brauchen nur einen Browser-Reload. Tests: `.venv/bin/python -m pytest`.

```
app/
  main.py           baut die FastAPI-App zusammen
  routes/           HTTP-Endpunkte je Bereich (workouts, plan, training, races, system)
  schemas.py        Eingabemodelle (Pydantic) – prüfen jede Anfrage
  services.py       Abläufe: Datenbank + Fachlogik + Übertragung verbinden
  db.py             SQLite und Standard-Einstellungen
  sync/             Garmin, intervals.icu, Zwift, Kalender-App – je push() / remove()
  …                 Fachlogik als reine Funktionen ohne Datenbank:
                    workouts, templates, load, periodization, recommend, compliance, feedback,
                    volume, nutrition, analysis, races, conflicts, plan_import, plan_prompt, availability
  mcp_server.py     MCP-Server für Claude (nutzt die HTTP-API)
  static/
    index.html, styles.css
    js/             Oberfläche als ES-Module, ein Modul je Bereich (main.js startet alles)
tests/              pytest, eine Datei je Bereich; jeder Test bekommt eine eigene leere Datenbank
docs/               ausführliche Beschreibung
```

**Erweitern:** neue Vorlage → `templates.py` (`TEMPLATES`); neues Ziel (z. B. TrainingPeaks) → Modul in `app/sync/`
mit `push()`/`remove()` und Eintrag in `app/sync/__init__.py`; neue Regel → `recommend.plan_days()` bzw. `analyze()`
mit Test in `tests/test_recommend.py`; neues MCP-Tool → `@server.tool(...)` in `mcp_server.py` (erwartbare Fehler als
`ToolError`).
