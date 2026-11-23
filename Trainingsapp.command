#!/bin/zsh
# Doppelklick im Finder startet die App und öffnet sie im Browser.
cd "$(dirname "$0")"

PORT=$(grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2)
PORT=${PORT:-8765}

source scripts/ensure_venv.sh

# Autostart für einen anderen Ordner eingerichtet oder App-Ordner verschoben → Dienst für diesen Ordner neu einrichten
if [ -f ~/Library/LaunchAgents/de.trainingsapp.plist ] && { autostart_elsewhere || venv_moved; }; then
  echo "Die App wurde verschoben – Hintergrunddienst wird für diesen Ordner neu eingerichtet …"
  exec zsh ./autostart.command
fi

# Als Hintergrunddienst eingerichtet (autostart.command)? Dann nur öffnen, kein zweiter Server.
if [ -f ~/Library/LaunchAgents/de.trainingsapp.plist ]; then
  # Neue Pakete installiert → Dienst neu starten, damit er sie lädt
  .venv/bin/pip install -r requirements.txt | grep -q "Successfully installed" \
    && launchctl kickstart -k "gui/$(id -u)/de.trainingsapp" && sleep 2
  open "http://127.0.0.1:$PORT"
  osascript -e 'tell application "Terminal" to close (every window whose name contains "Trainingsapp.command")' &
  exit 0
fi

ensure_venv

(sleep 1.5 && open "http://127.0.0.1:$PORT") &
echo "Trainingsapp läuft auf http://127.0.0.1:$PORT  (Beenden: Ctrl+C oder Fenster schließen)"
# --reload: Änderungen am Code (z. B. nach einem Update) werden ohne Neustart übernommen
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload --reload-dir app
