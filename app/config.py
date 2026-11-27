"""Pfade und Geheimnisse (.env). Alles andere steht in den Einstellungen in der DB."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
# Eigene Daten pro Installation (nicht im Git). TRAININGSAPP_DATA_DIR = anderer Ordner, z. B. für Tests oder ein
# zweites Profil auf demselben Computer.
DATA_DIR = Path(os.path.expanduser(os.getenv("TRAININGSAPP_DATA_DIR", ""))) if os.getenv("TRAININGSAPP_DATA_DIR") \
    else ROOT / "data"
DB_PATH = DATA_DIR / "training.db"
STATIC_DIR = ROOT / "app" / "static"


def venv_python(root: Path = ROOT, windows: bool = IS_WINDOWS) -> Path:
    """Python der App-Umgebung (.venv) – Windows legt es unter Scripts\\ ab, macOS/Linux unter bin/."""
    return root / ".venv" / ("Scripts/python.exe" if windows else "bin/python")


# So heißen die Starter im App-Ordner (für Hinweistexte)
START_SCRIPT = "Trainingsapp.bat" if IS_WINDOWS else "Trainingsapp.command"
UPDATE_SCRIPT = "Update.bat" if IS_WINDOWS else "Update.command"

# Garmin-Tokens liegen bewusst außerhalb des Projektordners (nicht im Git).
GARMIN_TOKEN_DIR = Path(os.path.expanduser("~/.trainingsapp/garmin_tokens"))


def _load_dotenv() -> None:
    """Minimaler .env-Loader (KEY=VALUE pro Zeile), damit keine Extra-Abhängigkeit nötig ist."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY", "")
INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "")
PORT = int(os.getenv("PORT", "8765"))
