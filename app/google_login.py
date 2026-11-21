"""Einmalige Google-Anmeldung für den Kalender-Sync:  .venv/bin/python -m app.google_login

Voraussetzung: OAuth-Client (Typ „Desktop-App“) aus der Google Cloud Console als
~/.trainingsapp/google_client_secret.json – Anleitung im README („Google Kalender“).
Der Browser öffnet sich, du meldest dich bei Google an und erlaubst den Zugriff auf deine Kalender.
Gespeichert wird nur das Token (~/.trainingsapp/google_token.json), nie dein Passwort.
"""
import sys

import httpx
from google_auth_oauthlib.flow import InstalledAppFlow

from . import config
from .sync.google_calendar import API, SCOPES


def main() -> None:
    if not config.GOOGLE_CLIENT_FILE.exists():
        sys.exit(f"OAuth-Client fehlt: {config.GOOGLE_CLIENT_FILE}\n"
                 "In der Google Cloud Console einen OAuth-Client vom Typ „Desktop-App“ anlegen, die JSON-Datei "
                 "herunterladen und unter diesem Namen speichern (siehe README, Abschnitt „Google Kalender“).")
    flow = InstalledAppFlow.from_client_secrets_file(str(config.GOOGLE_CLIENT_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  success_message="Angemeldet – du kannst dieses Fenster schließen.")
    config.GOOGLE_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.GOOGLE_TOKEN_FILE.write_text(creds.to_json())
    config.GOOGLE_TOKEN_FILE.chmod(0o600)

    r = httpx.get(f"{API}/users/me/calendarList", headers={"Authorization": f"Bearer {creds.token}"}, timeout=20)
    r.raise_for_status()
    names = [c.get("summary", "") for c in r.json().get("items", [])]
    print(f"Angemeldet. Token gespeichert in {config.GOOGLE_TOKEN_FILE}")
    print("Kalender:", ", ".join(names))
    if "Sport" in names:
        print("✔ Kalender „Sport“ gefunden – Workouts landen dort.")
    else:
        print("Hinweis: Kein Kalender „Sport“ gefunden. Den gewünschten Namen in den Einstellungen eintragen.")


if __name__ == "__main__":
    main()
