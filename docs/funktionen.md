# Funktionen im Detail

Wie die App rechnet und was die einzelnen Teile der Oberfläche tun. Kurzfassung in der [README](../README.md).

## Workouts

- **Klick auf einen Tag** → neues Workout. Vorlage wählen (Grundlage, Sweet Spot, Schwelle, VO2max …), Schritte
  anpassen, Vorschau und TSS sehen. Jeder Schritt kann ein eigenes Ziel haben (z. B. Einlaufen nach Puls, Intervalle nach
  Pace).
- **Klick auf ein geplantes Workout** → Details: Beschreibung, Uhrzeit (aus dem Namen, z. B. „08:00 · …“), Dauer, TSS,
  IF, Profil, Ablauf mit Watt/Pace und Ernährung (siehe unten). Von dort: Bearbeiten, Als erledigt markieren, bei
  Kraft/Stabi **▶ Workout starten**.
- **„Speichern & senden“** überträgt an die angehakten Geräte. Übertragene Workouts werden bei jeder Änderung (auch
  Verschieben per Drag & Drop) aktualisiert und beim Löschen auch dort entfernt.
- **Beim Öffnen** holt die App FTP, LTHR (Rad und Laufen getrennt), Max-Puls und Schwellentempo von Garmin (abschaltbar)
  sowie die Aktivitäten der letzten 14 Tage. Eine *neue* CSS-Messung von Garmin wird übernommen, ein eigener CSS-Wert
  sonst nicht überschrieben. **„Aktivitäten importieren“** holt 365 Tage plus Trainingsbereitschaft/HRV des Tages.

## Wochenübersicht (Wochenansicht)

Unter der Wochenansicht steht eine Statistik der Woche ([`volume.week_summary`](../app/volume.py)). Erledigtes zählt
mit echten Werten, noch Geplantes geschätzt, verpasste Workouts werden nur gezählt.

- **Tage** (unter den Kalenderspalten): Zeit, TSS und Balken nach Sportart; geplante Tage heller.
- **Je Sport**: Schwimmen und Laufen in km, sonst Stunden; Einheiten, davon erledigt, längste Einheit. Die Strecke
  geplanter Workouts kommt aus dem Namen („8–10 km“ → 9 km), sonst aus den Schritten (Tempo = Schwelle bzw. CSS ÷
  Intensität) – geschätzte Werte stehen mit „≈“.
- **Ausdauer gegen Soll** der Woche (Schwimmen + Rad + Laufen), **Intensität** locker / mittel / hart (erledigt aus den
  Pulszonen, geplant aus den Schritten; Grenzen Rad/Laufen 76 % und 88 %, Schwimmen 85 % und 98 % der CSS),
  **harte Einheiten** (mindestens 10 min über der Hart-Grenze), **Form am Ende der Woche** inklusive der geplanten
  Workouts.

## Abschnitte einer Einheit (Klick auf eine Aktivität)

Zwischenzeiten, Pace bzw. Leistung und Puls je Abschnitt, dazu je Intervall-Gruppe eine Kurzfassung
(„5 × 4:00 · Ø 1,02 km · Ø 3:55/km · Ø HF 183 · 5/5 im Ziel“) und die Gesamtwerte ([`app/laps.py`](../app/laps.py)).
Laufen: Pace/km, Puls, Kadenz · Rad: Watt, NP, Puls, Kadenz · Schwimmen: Pace/100 m, SWOLF, Züge, Lage.

- **Workout lief auf der Uhr**: Abschnitte = Workout-Schritte (Auto-Runden innerhalb eines Schritts werden
  zusammengefasst), jeder mit Ziel aus dem Plan; Intervalle und konstante Abschnitte werden grün/orange bewertet
  (2 % Spielraum, Pausen und Ein-/Auslaufen nicht). Ziele in Watt mit der FTP vom Tag der Einheit.
- **Rolle ohne Workout auf der Uhr** (z. B. Zwift): der Verlauf wird nach den geplanten Schrittdauern ab Start
  geschnitten.
- **Sonst** die Runden, wie aufgezeichnet; beim Schwimmen werden gleich lange Serien gruppiert (z. B. 6 × 100 m).

Runden und Verlauf holt die App beim ersten Öffnen von Garmin und speichert sie dauerhaft zwischen.

## Zirkel-Timer (Kraft/Stabi)

Im Workout **„▶ Zirkel-Timer“** oder oben **„⏱ Timer“** ohne Workout. Belastung und Pause in Sekunden, Runden (max. 60,
eine Runde = jede Übung einmal), Pause nach jeder Runde, Übungen (eine pro Zeile). Beim Stabi-Workout werden Übungen und
40/20 aus der Beschreibung übernommen.

- `Übung | 12 Wdh` = Wiederholungen: statt Countdown steht „12 Wdh“ da, weiter mit **„✓ Fertig“** (Leertaste/Enter).
  `| Wdh` ohne Zahl z. B. für „bis kurz vor Versagen“; `| 45 s` = eigene Dauer.
- Während des Laufs: aktuelle und nächste Übung groß, Farbe je Phase, Piepton bei 3-2-1, Ansage, Bildschirm bleibt an.
  Leertaste = Pause, ← / → = zurück / überspringen. Am Ende „Als erledigt speichern“ – der Zirkel bleibt am Workout.
- An Garmin geht derselbe Zirkel: je Übung ein Schritt mit Garmin-Übung aus dem Katalog (`EXERCISES` in
  [`app/sync/garmin.py`](../app/sync/garmin.py), unbekannte nur als Notiz), Wiederholungen als Wdh-Ziel bzw. per
  Runden-Taste, Pausen, Rundenpause.

## Ernährung vor · während · nach

Kohlenhydrate, Flüssigkeit, Eiweiß, Zeitpunkt und Tagesziel je Einheit. Gerechnet mit Gewicht und Schweißrate aus den
Einstellungen, Art der Einheit, Wochen bis zum Wettkampf (Darmtraining) und den anderen Einheiten am Tag (Koppellauf,
Qualität in < 8 h → schnell auffüllen). Steht in der Beschreibung ein Block „KH (… kg): – Vorher: … – Während: … –
Danach: …“, gelten dessen Zahlen. Regeln in [`app/nutrition.py`](../app/nutrition.py).

## Auswertung

- **Compliance** (wie TrainingPeaks): farbiger Streifen an geplanten Workouts – grün 80–120 % der geplanten Dauer, gelb
  50–79 % / 121–150 %, orange darüber/darunter, rot = verpasst. Ungeplante Aktivitäten sind gestrichelt.
- **Training erkennen** ([`app/compliance.py`](../app/compliance.py)): Eine importierte Aktivität wird dem Workout
  desselben Tags und Sports zugeordnet, wenn es grob passt: gleicher Name, oder Dauer ungefähr gleich (60–160 %,
  Schwimmen 50–200 %, Stabi/Dehnen 40–200 %) und die Härte stimmt (Pulszonen, Leistung, Max-Puls gegen die
  Laktatschwelle des Sports). Sonst zeigt das Workout „≠ anders als geplant“. Liegt die Erkennung daneben: Klick auf die
  Aktivität → **Geplantes Workout** von Hand wählen.
- **Feedback** ([`app/feedback.py`](../app/feedback.py)): Klick auf eine Aktivität → RPE (0–10), Befinden (1–5), Notiz.
  Lockere Einheit mit RPE ≥ 8 → 2 Tage nichts Hartes; Ø-RPE ≥ 7 bei Ermüdung → 2 Tage reduziert; harte Einheiten mit
  RPE ≤ 3 → Hinweis, die Schwellen zu testen.
- **Analyse** (Knopf oben):
  - *Kennzahlen* von Garmin: Trainingsstatus, VO2max, Endurance Score, Hitzeanpassung, Renn-Prognosen,
    FTP-/VO2max-Verlauf (6 h zwischengespeichert, „↻ Garmin“ lädt neu).
  - *Leistungskurve* 90 vs. 365 Tage mit FTP-Schätzungen (95 % von 20 min, Critical Power, 60 min).
  - *Effizienz*: Watt bzw. Tempo bei gleichem Puls (Referenzpuls) lockerer Einheiten mit 28-Tage-Trend.
  - *Zonen*: Zeit in Pulszonen pro Woche und Anteil locker (80/20).
  - *Renntag*: Zielwerte, Zeiten und Verpflegung je Disziplin (Annahmen in `RACE_DEFAULTS`,
    [`app/static/js/raceday.js`](../app/static/js/raceday.js)).

Alle Analysen nutzen die Garmin-Zusammenfassungen der Aktivitäten (Puls, NP, Zonen, Bestleistungen) – Sekundendaten
werden nicht geladen.

## Saisonplanung und Wettkämpfe

**Ziel-CTL** vor dem Tapering (Einstellungen) → nötiger Anstieg pro Woche, Risiko (`periodization.RAMP_RISK`) und nötige
Wochen-TSS/-Stunden in der Blockkarte.

Weitere Wettkämpfe als **B** (Mini-Taper + volle Erholung) oder **C** (durchtrainiert, Erholung ×0,6). Taper, Erholung
und Laufpause hängen von der Distanz ab ([`app/races.py`](../app/races.py)):

| Distanz (B) | Mini-Taper | Erholung (davon nur Regeneration) | Laufpause |
|---|---|---|---|
| Lauf 5 km / 10 km | 2 / 3 Tage | 2 / 3 (0 / 1) Tage | – |
| Halbmarathon | 4 Tage | 7 (1) Tage | 2 Tage |
| Marathon | 7 Tage | 14 (3) Tage | 5 Tage |
| Ultralauf | 7 Tage | 21 (4) Tage | 7 Tage |
| Triathlon Sprint / Olympisch | 2 / 3 Tage | 2 / 4 (0 / 1) Tage | – / 1 Tag |
| 70.3 / Ironman | 4 / 10 Tage | 7 / 21 (2 / 4) Tage | 3 / 7 Tage |

In der Laufpause schlägt die App lockeres Rad statt Laufen vor; nach der Regenerationsphase steigt der Umfang von 70 %
auf 90 %, harte Einheiten erst nach Ende der Erholung.

**Konflikte** ([`app/conflicts.py`](../app/conflicts.py)): Geplante Workouts werden nie automatisch geändert. Passt
eines nicht zu Taper, Renntag, Regeneration, Erholung oder Laufpause eines Wettkampfs (auch des A-Rennens, dort nur die
letzten 3 Tage und danach), ist es mit ⚠ markiert und erscheint in der Seitenleiste mit Vorschlag („Schwelle →
Grundlage 60 min“, „Laufen → Rad locker“, „entfernen“). „Anpassen“ übernimmt ihn, auch auf den Geräten.

## Wie die Vorschläge entstehen

Bewusst regelbasiert und nachvollziehbar, jeder Vorschlag hat eine Begründung. Bereits geplante Workouts werden nie
überschrieben, sondern fließen in die Simulation ein.

1. **Periodisierung** ([`app/periodization.py`](../app/periodization.py)), rückwärts vom Wettkampf gezählt. Ironman:
   Grundlage → Aufbau 1 (8 Wo) → Aufbau 2 (8 Wo) → Wettkampfspezifisch (8 Wo) → Tapering (3 Wo inkl. Rennwoche) →
   2 Wochen Regeneration. Für 70.3 und andere Wettkämpfe gibt es kürzere Pläne.
   - **Belastung/Entlastung**: z. B. 3 Wochen steigend (90 % → 100 % → 110 %), dann 1 Woche Entlastung (60 %). Der
     Rhythmus ist am Wettkampf ausgerichtet: die letzte Woche vor dem Tapering ist die härteste. Mit **Zyklusstart**
     zählt er stattdessen ab einem festen Montag vorwärts; Wochen davor gelten als Vorlauf. **Taper-Wochen** überschreibt
     die Taper-Länge.
   - **Wochenstunden** (Schwimmen + Rad + Laufen) = eingestellte Stunden × Blockfaktor × Wochenfaktor. Stabi und Dehnen
     kommen obendrauf.
   - **Hitzetraining** ab ca. 6 Wochen vor dem Rennen: 3–4 lockere Rad-/Laufeinheiten pro Woche, in der Woche vor dem
     Rennen 2, in der Rennwoche keine.
2. **Wochenmuster**: pro Tag beliebig viele Einheiten (Sport + Typ). Geplante Workouts und heute erledigte Aktivitäten
   belegen passende Einheiten, die freien bekommen Vorschläge. Die Wochenstunden werden nach Gewicht (Typ × Sport)
   verteilt. Verpasste Einheiten werden nicht auf die restlichen Tage gepackt.
3. **Harte Einheiten** rotieren je Block (Grundlage: Sweet Spot/Tempo, Aufbau: Schwelle/VO2max, Wettkampfspezifisch:
   Wettkampftempo/Schwelle). Lange Einheiten wechseln im wettkampfspezifischen Block mit Wettkampftempo-Einheiten.
4. **Regeln** (Tag für Tag mit simulierter Belastung, [`app/recommend.py`](../app/recommend.py)):
   - keine harte Einheit derselben Sportart am Vor- oder Folgetag einer harten Einheit
   - höchstens eine harte Rad-/Laufeinheit pro Tag (beide Abstandsregeln entfallen mit `own_spacing_rules`)
   - Entlastungswoche: Intensität raus
   - keine Intensität bei TSB < −25, nur Regeneration bei TSB < −35
   - heute lockerer bei niedriger Trainingsbereitschaft oder schlechter HRV (Garmin)
   - Koppellauf nach dem langen Rad ab Aufbau 2; Verpflegungshinweis (60–90 g KH/h) bei langen Einheiten ab Aufbau 2
   - Rennwoche: kein Stabi in den letzten 10 Tagen, Aktivierung 3 Tage und 1 Tag vorher, Ruhetag 2 Tage vorher
5. **Warnungen**: zu schnelle Rampe (> 8 CTL/Woche), kein Ruhetag in 7 Tagen, mehr als 25 % intensive Ausdauerzeit.

**Anpassen**: Blocklängen in `RACE_PLANS`, Umfang in `BLOCK_VOLUME`/`TAPER_VOLUME`, Hitzetraining in `HEAT_SESSIONS`
(alle in `periodization.py`); Gewichte, Rotation und Regeln in `recommend.py`; Zonen und Intervalle in `templates.py`.

## Kalender-App (iCloud, Outlook & Co.)

Geplante Workouts landen als ganztägige Termine in einem Kalender deiner Wahl – Titel „Sportart – Programm“, Beschreibung
mit allen Schritten in Watt / Pace / Puls, Dauer und TSS. Die App schreibt in die Kalender-App des Macs; liegt der
Kalender bei iCloud oder einem anderen Konto, synchronisiert macOS ihn selbst weiter (der Mac muss dafür an sein).
Fehlt die Berechtigung („… möchte Kalender steuern“), pausiert die App das Eintragen kurz, statt bei jedem Speichern zu
hängen. Nachträglich erlauben: *Systemeinstellungen → Datenschutz & Sicherheit → Automation*.

Nur auf dem Mac – unter Windows blendet die App das Eintragen aus. Freie Zeiten per iCal-Link (iCloud, Outlook, Google)
liest sie dort genauso.

## Windows

Die Starter `Trainingsapp.bat`, `Update.bat` und `Autostart.bat` rufen `scripts/launcher.py` auf (nur
Standardbibliothek, läuft also schon vor der `.venv`). Er legt die Umgebung unter `.venv\Scripts\` an, installiert
Pakete nur, wenn sich `requirements.txt` geändert hat, und startet den Server mit `--reload`.

Der **Autostart** braucht keine Administratorrechte: `Trainingsapp.vbs` im Autostart-Ordner des Benutzers
(`shell:startup`) startet beim Anmelden `launcher.py serve` ohne Fenster. Der Dienst schreibt ins Log
`%LOCALAPPDATA%\Trainingsapp\trainingsapp.log` und startet den Server nach einem Absturz neu (höchstens fünfmal in
zehn Minuten). Läuft die App gerade in einem Fenster, beendet der Dienst diesen Server und übernimmt. Welcher Prozess
den Server betreibt, steht in `%LOCALAPPDATA%\Trainingsapp\server-<port>.json` – so beendet die App nie ein fremdes
Programm. Code: `app/winservice.py`, Tests: `tests/test_windows.py`; GitHub Actions prüft Start, Übernahme durch den
Dienst und Abschalten auf einem echten Windows.

Warum Wahoo über intervals.icu? Die Wahoo-Cloud-API braucht einen freigeschalteten Entwickler-Account; intervals.icu
ist offiziell angebunden und liefert zusätzlich Aktivitäten mit Trainingslast.
