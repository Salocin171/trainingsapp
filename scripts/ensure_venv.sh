# Gemeinsame Einrichtung für Trainingsapp.command, autostart.command und Update.command (wird per "source" geladen).
# Sucht ein Python ab 3.12 (macOS bringt nur 3.9 mit), legt .venv an und installiert die Pakete.

MIN_MINOR=12
PYTHON_URL="https://www.python.org/downloads/macos/"

find_python() {
  local candidates=(
    python3.14 python3.13 python3.12
    /Library/Frameworks/Python.framework/Versions/3.1{4,3,2}/bin/python3
    /opt/homebrew/bin/python3 /usr/local/bin/python3 python3
  )
  for py in $candidates; do
    command -v "$py" >/dev/null 2>&1 || continue
    if "$py" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_MINOR) else 1)" 2>/dev/null; then
      echo "$py"; return 0
    fi
  done
  return 1
}

# Ordner verschoben (z. B. aus Downloads)? Die Umgebung enthält feste Pfade und funktioniert dann nicht mehr.
venv_moved() {
  [ -d .venv ] && ! head -2 .venv/bin/pip 2>/dev/null | grep -qF "$(pwd -P)/.venv/bin/"
}

ensure_venv() {
  if venv_moved; then
    echo "Der App-Ordner wurde verschoben – Python-Umgebung wird neu eingerichtet …"
    rm -rf .venv
  fi
  # Vorhandene Umgebung mit zu altem Python ersetzen
  if [ -x .venv/bin/python ] && ! .venv/bin/python -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_MINOR) else 1)"; then
    echo "Python-Umgebung ist zu alt – wird neu angelegt …"
    rm -rf .venv
  fi
  if [ ! -d .venv ]; then
    local py
    py=$(find_python) || {
      echo ""
      echo "Für die Trainingsapp wird Python 3.$MIN_MINOR oder neuer gebraucht (macOS bringt nur eine ältere Version mit)."
      echo "1. Auf der Seite, die sich gleich öffnet, den neuesten „macOS 64-bit universal2 installer“ laden."
      echo "2. Die .pkg-Datei öffnen und durchklicken."
      echo "3. Danach Trainingsapp.command noch einmal doppelklicken."
      open "$PYTHON_URL"
      echo ""; read -k1 "?Taste drücken zum Schließen …"; exit 1
    }
    echo "Erster Start: Python-Umgebung wird eingerichtet ($("$py" --version)) – dauert ca. eine Minute …"
    "$py" -m venv .venv || { echo "Einrichten fehlgeschlagen."; read -k1; exit 1; }
    .venv/bin/pip install -q --upgrade pip
  fi
  .venv/bin/pip install -q -r requirements.txt || { echo "Pakete konnten nicht installiert werden (Internet?)."; read -k1; exit 1; }
}

# Autostart (autostart.command) eingerichtet, aber für einen anderen Ordner (App verschoben oder zweite Kopie)?
# Liefert 0, wenn der Dienst neu eingerichtet werden muss.
autostart_elsewhere() {
  local plist=~/Library/LaunchAgents/de.trainingsapp.plist dir
  [ -f "$plist" ] || return 1
  dir=$(plutil -extract WorkingDirectory raw "$plist" 2>/dev/null)
  [ "$(cd "$dir" 2>/dev/null && pwd -P)" != "$(pwd -P)" ]
}
