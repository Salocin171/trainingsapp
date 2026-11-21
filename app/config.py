"""Pfade und Geheimnisse (.env). Alles andere steht in den Einstellungen in der DB."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Eigene Daten pro Installation (nicht im Git). TRAININGSAPP_DATA_DIR = anderer Ordner, z. B. für Tests oder ein
# zweites Profil auf demselben Mac.
DATA_DIR = Path(os.path.expanduser(os.getenv("TRAININGSAPP_DATA_DIR", ""))) if os.getenv("TRAININGSAPP_DATA_DIR") \
    else ROOT / "data"
DB_PATH = DATA_DIR / "training.db"
STATIC_DIR = ROOT / "app" / "static"

# Garmin-Tokens liegen bewusst außerhalb des Projektordners (nicht im Git).
GARMIN_TOKEN_DIR = Path(os.path.expanduser("~/.trainingsapp/garmin_tokens"))


def _load_dotenv() -> None:
    """Minimaler .env-Loader (KEY=VALUE pro Zeile), damit keine Extra-Abhängigkeit nötig ist."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

INTERVALS_API_KEY = os.getenv("INTERVALS_API_KEY", "")
INTERVALS_ATHLETE_ID = os.getenv("INTERVALS_ATHLETE_ID", "")
PORT = int(os.getenv("PORT", "8765"))
