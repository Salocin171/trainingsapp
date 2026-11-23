#!/bin/zsh
# Doppelklick: neueste Version von GitHub holen. Deine Daten (Ordner data/ und ~/.trainingsapp) bleiben unverändert.
# Funktioniert auch, wenn die App als ZIP heruntergeladen wurde (dann ohne .git-Ordner).
cd "$(dirname "$0")"
REPO="https://github.com/Salocin171/trainingsapp"

fail() {
  echo ""
  echo "$1"
  echo "Deine Trainingsdaten sind davon nicht betroffen. Im Zweifel die Person fragen, von der du die App hast."
  read -k1 "?Taste drücken zum Schließen …"; exit 1
}

echo "Hole die neueste Version der Trainingsapp …"
if [ -d .git ]; then
  git pull --ff-only || fail "Update nicht möglich – vermutlich wurden Dateien der App von Hand geändert."
elif xcode-select -p >/dev/null 2>&1; then
  # Als ZIP geladen, git ist da: Ordner einmalig mit GitHub verbinden – künftige Updates laufen dann per git pull.
  # data/ und .venv/ stehen in .gitignore und bleiben unberührt.
  { git init -q && git remote add origin "$REPO.git" && git fetch -q origin main \
    && git checkout -q -f -B main origin/main; } || { rm -rf .git; fail "Update nicht möglich (keine Verbindung zu GitHub?)."; }
else
  # Ohne git: aktuelle Version als ZIP laden und die App-Dateien ersetzen (data/ und .venv/ bleiben).
  tmp=$(mktemp -d)
  curl -fsSL "$REPO/archive/refs/heads/main.zip" -o "$tmp/app.zip" && unzip -q "$tmp/app.zip" -d "$tmp" \
    || { rm -rf "$tmp"; fail "Update nicht möglich (keine Verbindung zu GitHub?)."; }
  rsync -a --exclude data/ --exclude .venv/ "$tmp/trainingsapp-main/" ./
  rm -rf "$tmp"
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
