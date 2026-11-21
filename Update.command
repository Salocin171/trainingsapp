#!/bin/zsh
# Doppelklick: neueste Version von GitHub holen. Deine Daten (Ordner data/ und ~/.trainingsapp) bleiben unverändert.
cd "$(dirname "$0")"

echo "Hole die neueste Version der Trainingsapp …"
if ! git pull --ff-only; then
  echo ""
  echo "Update nicht möglich – vermutlich wurden Dateien der App von Hand geändert."
  echo "Deine Trainingsdaten sind davon nicht betroffen. Im Zweifel die Person fragen, von der du die App hast."
  read -k1 "?Taste drücken zum Schließen …"; exit 1
fi

source scripts/ensure_venv.sh
ensure_venv

# Läuft die App als Hintergrunddienst (autostart.command)? Dann neu starten, damit sie die neue Version lädt.
if [ -f ~/Library/LaunchAgents/de.trainingsapp.plist ]; then
  launchctl kickstart -k "gui/$(id -u)/de.trainingsapp"
fi
echo ""
echo "Fertig. Läuft die App gerade im Terminal, dort mit Ctrl+C beenden und Trainingsapp.command neu starten;"
echo "sonst einfach den Browser neu laden."
read -k1 "?Taste drücken zum Schließen …"
