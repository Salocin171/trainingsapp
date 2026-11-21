"""Einmalige Garmin-Anmeldung im Terminal:  .venv/bin/python -m app.garmin_login

Passwort wird nicht gespeichert, nur die Sitzungs-Tokens (~/.trainingsapp/garmin_tokens).
"""
import getpass

from garminconnect import Garmin

from . import config


def main() -> None:
    email = input("Garmin-E-Mail: ").strip()
    password = getpass.getpass("Garmin-Passwort: ")
    g = Garmin(email, password, prompt_mfa=lambda: input("MFA-Code: ").strip())
    config.GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    g.login(str(config.GARMIN_TOKEN_DIR))
    g.client.dump(str(config.GARMIN_TOKEN_DIR))
    print(f"Angemeldet als {g.get_full_name()}. Tokens gespeichert in {config.GARMIN_TOKEN_DIR}")


if __name__ == "__main__":
    main()
