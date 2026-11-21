#!/bin/zsh
# Doppelklick im Finder: Trainingsapp als Hintergrunddienst (LaunchAgent) einrichten –
# startet beim Anmelden, ohne Terminalfenster, und nach einem Absturz neu.
# Entfernen: ./autostart.command off
cd "$(dirname "$0")"

LABEL=de.trainingsapp
PLIST=~/Library/LaunchAgents/$LABEL.plist
LOG=~/Library/Logs/trainingsapp.log
DOMAIN=gui/$(id -u)

launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null  # alte Version des Dienstes stoppen

if [ "$1" = "off" ]; then
  rm -f "$PLIST"
  echo "Autostart entfernt. Starten wieder per Doppelklick auf Trainingsapp.command."
  exit 0
fi

source scripts/ensure_venv.sh
ensure_venv

PORT=$(grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2)
PORT=${PORT:-8765}

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT ist belegt – läuft die App noch in einem Terminal? Dort mit Ctrl+C beenden und erneut starten."
  read; exit 1
fi

mkdir -p ~/Library/LaunchAgents ~/Library/Logs
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>WorkingDirectory</key><string>$PWD</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PWD/.venv/bin/uvicorn</string>
    <string>app.main:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>$PORT</string>
    <string>--reload</string><string>--reload-dir</string><string>app</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootstrap "$DOMAIN" "$PLIST" || { echo "Dienst konnte nicht gestartet werden."; read; exit 1; }

for _ in {1..20}; do
  curl -s -o /dev/null "http://127.0.0.1:$PORT" && break
  sleep 0.5
done
echo "✔ Trainingsapp läuft im Hintergrund auf http://127.0.0.1:$PORT (Log: $LOG)"
open "http://127.0.0.1:$PORT"
