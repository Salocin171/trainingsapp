"""Einstellungen, Verbindungen, Import, Analyse, Einrichtung, Autostart und Updates."""
from fastapi import APIRouter, HTTPException

from .. import autostart, db, periodization, plan_import, services, updater
from ..schemas import GarminLoginIn, SettingsIn
from ..sync import TARGETS
from ..workouts import FLAT_TSS_PER_HOUR

router = APIRouter(prefix="/api")


@router.get("/meta")
def meta():
    """Konstanten, die auch die Oberfläche braucht – damit sie nicht doppelt in app.js stehen."""
    return {
        "flat_tss_per_hour": FLAT_TSS_PER_HOUR,
        "circuit_limits": plan_import.CIRCUIT_LIMITS,
        "exercise_limits": plan_import.EXERCISE_LIMITS,
        "race_types": periodization.RACE_TYPES,
    }


# --- Einstellungen & Status --------------------------------------------------

@router.get("/settings")
def get_settings():
    return db.get_settings()


@router.put("/settings")
def put_settings(values: SettingsIn):
    return db.save_settings(values.model_dump(exclude_unset=True))


@router.post("/settings/garmin")
def refresh_settings_from_garmin():
    """Leistungswerte aus Garmin übernehmen (die Oberfläche ruft das bei jedem Öffnen auf)."""
    return services.refresh_settings_from_garmin()


@router.get("/status")
def get_status():
    return services.connected()


@router.get("/calendars")
def mac_calendars():
    """Kalender der Kalender-App des Macs (für die Auswahl, wohin Trainings eingetragen werden)."""
    try:
        return TARGETS["calendar"].calendars()
    except Exception as e:  # noqa: BLE001 – z. B. fehlende Berechtigung
        raise HTTPException(502, str(e)) from e


# --- Import & Analyse ----------------------------------------------------------

@router.post("/import/{source}")
def import_data(source: str, days: int = 120):
    return {"imported": services.import_activities(source, days)}


@router.get("/analysis")
def get_analysis(refresh: bool = False):
    """Efficiency Factor, Zonen, Leistungskurve (aus importierten Aktivitäten) und Garmin-Kennzahlen (gecacht)."""
    return services.analysis_data(refresh)


# --- Einrichtung (erster Start) und Autostart -----------------------------------

@router.post("/setup/garmin")
def setup_garmin(body: GarminLoginIn):
    return services.setup_garmin(body.email, body.password, body.code)


@router.get("/setup/autostart")
def autostart_status():
    return autostart.status()


@router.post("/setup/autostart")
def autostart_install():
    try:
        return autostart.install()
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from None


# --- Updates von GitHub --------------------------------------------------------

@router.get("/update")
def update_status(force: bool = False):
    return updater.status(force)


@router.post("/update")
def update_apply():
    try:
        return updater.apply()
    except updater.UpdateError as e:
        raise HTTPException(409, str(e)) from None
