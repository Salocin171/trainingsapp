# Trainingsapp

Trainingsplanung für Triathlon und Ironman, lokal auf deinem Computer: Kalender mit mehreren Einheiten pro Tag,
Workout-Editor, Periodisierung bis zum Wettkampf, Vorschläge mit Begründung, Ernährung je Einheit, Auswertung – und
Übertragung auf **Garmin**, **Wahoo** (über intervals.icu), **Zwift** und die **Kalender-App** (Mac). Claude kann die
App per MCP bedienen.

Für **macOS** und **Windows**. Läuft als kleiner Python-Server, bedient wird sie im Browser.

## Installation auf dem Mac (einmalig, ca. 10 Minuten)

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

## Installation unter Windows (einmalig, ca. 10 Minuten)

1. **Herunterladen:** auf [github.com/Salocin171/trainingsapp](https://github.com/Salocin171/trainingsapp) *Code →
   Download ZIP*, entpacken (Rechtsklick → „Alle extrahieren“) und den Ordner dorthin legen, wo er bleiben soll, z. B.
   `C:\Users\DEIN-NAME\Trainingsapp`. Mit [Git](https://git-scm.com/download/win) geht auch
   `git clone https://github.com/Salocin171/trainingsapp.git %USERPROFILE%\Trainingsapp`.
2. **Starten:** **`Trainingsapp.bat` doppelklicken.** Warnt Windows („Der Computer wurde durch Windows geschützt“):
   *Weitere Informationen → Trotzdem ausführen*. Fehlt Python 3.12+, öffnet sich python.org: „Download Python“, im
   Installer unten **„Add python.exe to PATH“** anhaken, „Install Now“, dann erneut doppelklicken. Beim ersten Mal wird
   alles eingerichtet (ca. eine Minute), danach öffnet sich der Browser.
3. **Einrichten:** wie auf dem Mac (Garmin, Schwellen, Saisonziel). Tipp: In Edge *⋯ → Apps → Diese Website als App
   installieren* – dann ist die App ein eigenes Programm im Startmenü.
4. **Autostart** (empfohlen): in der Einrichtung **„Autostart einrichten“** oder `Autostart.bat` doppelklicken. Die App
   läuft dann ohne Fenster im Hintergrund und startet beim Anmelden. Log: `%LOCALAPPDATA%\Trainingsapp\trainingsapp.log`,
   entfernen: `Autostart.bat off` (Eingabeaufforderung im App-Ordner).

Updates wie auf dem Mac über **„⬆ Update“**; bei einer als ZIP geladenen App `Update.bat` doppelklicken (mit Git
verbindet es den Ordner dabei einmalig mit GitHub, danach geht auch der Knopf). Die Kalender-App-Anbindung gibt es nur
auf dem Mac; freie Zeiten per iCal-Link (Outlook, Google, iCloud) funktionieren auch unter Windows.

## Deine Daten

**Deine Daten** bleiben auf deinem Computer und sind nicht im Git: Trainingsdaten in `data/training.db` (zum Sichern
kopieren), Garmin-Anmeldung in `~/.trainingsapp/` (Windows:
`%USERPROFILE%\.trainingsapp\`). Zweites Profil zum Ausprobieren (Mac):
`TRAININGSAPP_DATA_DIR=~/Trainingsapp-Test ./Trainingsapp.command`.

> Die Garmin-Anbindung nutzt die inoffizielle Bibliothek [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
> und kann jederzeit brechen (dann meist `pip install -U garminconnect`). Ernährungswerte sind Richtwerte, keine
> medizinische Beratung.

## Geräte verbinden

| Ziel | Weg | Einrichtung |
|---|---|---|
| **Garmin** (Uhr / Edge) | Workout im Garmin-Connect-Kalender, das Gerät lädt es beim Sync | Einrichtungsdialog, oder `.venv/bin/python -m app.garmin_login` (Windows: `.venv\Scripts\python.exe -m app.garmin_login`) |
| **Wahoo** | über [intervals.icu](https://intervals.icu) (kostenlos) | intervals.icu: Wahoo verbinden, „Upload planned workouts“ an. API-Key + Athleten-ID in `.env` (Vorlage `.env.example`) |
| **Zwift** | `.zwo`-Datei, erscheint unter *Custom Workouts* | nichts – der Ordner wird gefunden, auch unter OneDrive (sonst in den Einstellungen setzen); macOS fragt evtl. nach Zugriff auf *Dokumente* → Erlauben |
| **Kalender** (iCloud, Outlook …) – nur Mac | ganztägige Termine über die Kalender-App des Macs | *Einstellungen → Automatisch senden → Kalender* und Kalender wählen; macOS-Abfrage „… möchte Kalender steuern“ mit OK bestätigen |

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

Windows (PowerShell im App-Ordner):

```powershell
claude mcp add trainingsapp --scope user -- "$PWD\.venv\Scripts\python.exe" "$PWD\app\mcp_server.py"
```

**Claude Desktop**: *Einstellungen → Entwickler → Konfiguration bearbeiten*, eintragen, neu starten:

```json
{ "mcpServers": { "trainingsapp": {
    "command": "/Users/DEIN-BENUTZERNAME/Trainingsapp/.venv/bin/python",
    "args": ["/Users/DEIN-BENUTZERNAME/Trainingsapp/app/mcp_server.py"] } } }
```

Unter Windows mit `"C:\\Users\\DEIN-NAME\\Trainingsapp\\.venv\\Scripts\\python.exe"` und
`"C:\\Users\\DEIN-NAME\\Trainingsapp\\app\\mcp_server.py"` (doppelte Backslashes im JSON).

Tools: Status, Kalender, Workouts anlegen/ändern/löschen und senden, Vorschläge, Plan-Brief und Plan-Import, Analyse,
Feedback, Einstellungen, Wettkämpfe und Konflikte, Aktivitäten importieren. Zum Block planen spart `get_plan_brief`
Tokens (alle Vorgaben in einem Text); `import_plan` prüft zuerst und importiert dann per `preview_id`.

## Entwicklung

In VS Code **F5** → „Trainingsapp (Server mit Reload)“. Python-Änderungen laden den Server neu, Änderungen in
`app/static/` brauchen nur einen Browser-Reload. Tests: `.venv/bin/python -m pytest` – GitHub Actions führt sie bei
jedem Push auf macOS und Windows aus und startet die App dort einmal wie per Doppelklick.

```
app/
  main.py           baut die FastAPI-App zusammen
  routes/           HTTP-Endpunkte je Bereich (workouts, plan, training, races, system)
  schemas.py        Eingabemodelle (Pydantic) – prüfen jede Anfrage
  services.py       Abläufe: Datenbank + Fachlogik + Übertragung verbinden
  db.py             SQLite und Standard-Einstellungen
  autostart.py      Hintergrunddienst einrichten (Mac: LaunchAgent, Windows: winservice.py)
  sync/             Garmin, intervals.icu, Zwift, Kalender-App – je push() / remove()
  …                 Fachlogik als reine Funktionen ohne Datenbank:
                    workouts, templates, load, periodization, recommend, compliance, feedback,
                    volume, nutrition, analysis, races, conflicts, plan_import, plan_prompt, availability
  mcp_server.py     MCP-Server für Claude (nutzt die HTTP-API)
  static/
    index.html, styles.css
    js/             Oberfläche als ES-Module, ein Modul je Bereich (main.js startet alles)
scripts/            Mac: ensure_venv.sh · Windows: launcher.py (Start, Update, Autostart) und find_python.bat
tests/              pytest, eine Datei je Bereich; jeder Test bekommt eine eigene leere Datenbank
docs/               ausführliche Beschreibung
```

**Erweitern:** neue Vorlage → `templates.py` (`TEMPLATES`); neues Ziel (z. B. TrainingPeaks) → Modul in `app/sync/`
mit `push()`/`remove()` und Eintrag in `app/sync/__init__.py`; neue Regel → `recommend.plan_days()` bzw. `analyze()`
mit Test in `tests/test_recommend.py`; neues MCP-Tool → `@server.tool(...)` in `mcp_server.py` (erwartbare Fehler als
`ToolError`).
