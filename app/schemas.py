"""Eingabemodelle der API (Pydantic). FastAPI prüft damit jede Anfrage, bevor eine Route sie sieht."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .sync import TARGETS
from .workouts import SPORTS

# --- Workouts ----------------------------------------------------------------


class WorkoutIn(BaseModel):
    id: int | None = None
    date: str
    sport: str = "ride"
    name: str = "Workout"
    description: str = ""
    target: str = "power"
    template: str = ""
    steps: list[dict] = []
    status: str = "planned"
    actual_tss: float | None = None
    rpe: float | None = None     # Anstrengung 0–10 (nach der Einheit)
    feel: int | None = None      # Befinden 1–5
    note: str = ""
    circuit: dict | None = None  # Zirkel-Timer: work/rest/round_rest (s), rounds, exercises


class FeedbackIn(BaseModel):
    rpe: float | None = None
    feel: int | None = None
    note: str = ""


class PlanLinkIn(BaseModel):
    workout_id: int | None = None  # None = automatisch erkennen, 0 = gehört zu keinem Workout


class SyncIn(BaseModel):
    targets: list[str]


class BulkSyncIn(BaseModel):
    target: str
    days: int = 120       # ab heute
    resend: bool = False  # auch schon übertragene erneut senden (Kalender: fehlende/kaputte Termine reparieren)


# --- Plan-Import -------------------------------------------------------------


class PlanIn(BaseModel):
    plan: dict
    start: str | None = None  # Montag der 1. Woche; überschreibt "start" im Plan
    replace: bool = False     # geplante (nicht erledigte) Workouts im Zeitraum vorher löschen


class PromptIn(BaseModel):
    start: str = ""
    weeks: int = 4
    notes: str = ""


# --- Wettkämpfe, Konflikte, Ziele -------------------------------------------


class ApplyConflictsIn(BaseModel):
    workout_ids: list[int]


class RaceIn(BaseModel):
    id: int | None = None
    name: str
    date: str
    priority: str = "B"       # B = Mini-Taper + Erholung, C = durchtrainieren
    race_type: str = "other"  # Schlüssel aus races.DISTANCES (z. B. run_marathon, half) → Taper/Erholung


class GoalIn(BaseModel):
    id: int | None = None
    name: str = ""
    sport: str = "all"     # all | swim | ride | run | strength | mobility
    metric: str = "hours"  # hours | km
    period: str = "week"   # week | month | year | custom
    target: float
    start: str = ""        # nur bei period = custom
    end: str = ""


# --- Einrichtung & Einstellungen --------------------------------------------


class GarminLoginIn(BaseModel):
    email: str = ""
    password: str = ""
    code: str = ""  # MFA-Code im zweiten Schritt


Number = Annotated[int | float, Field(ge=0)]  # int bleibt int (FTP 250, nicht 250.0)


class PatternSlot(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: Literal["recovery", "easy", "hard", "long"]
    sport: Literal[SPORTS]


class SettingsIn(BaseModel):
    """Teil-Update der Einstellungen: nur mitgeschickte Felder werden gespeichert (model_dump(exclude_unset=True)).

    Der Vorgabewert None wird nicht geprüft und steht nur für „nicht mitgeschickt“ – ein ausdrückliches null wird
    abgelehnt. Felder müssen zu db.DEFAULT_SETTINGS passen (Test: test_settings_model_matches_defaults)."""
    model_config = ConfigDict(extra="forbid")

    ftp: Number = None
    lthr_run: Number = None
    lthr_ride: Number = None
    max_hr: Number = None
    threshold_pace: Number = None
    css: Number = None
    zwift_dir: str = None
    race_type: Literal["ironman", "half", "other"] = None
    goal_name: str = None
    goal_date: str = None
    week_hours: Number = None
    recovery_every: Annotated[int, Field(ge=0)] = None
    cycle_start: str = None
    taper_weeks: Annotated[int, Field(ge=0)] = None
    auto_sync: list[Literal[tuple(TARGETS)]] = None
    mac_calendar: str = None
    garmin_profile: bool = None
    garmin_profile_at: str = None
    css_garmin_seen: str = None
    target_ctl: Number = None
    weight: Number = None
    sweat_rate: Number = None
    plant_based: bool = None
    own_spacing_rules: bool = None
    setup_done: bool = None
    calendar_ics: list[str] = None
    availability: str = None
    race_plan: dict = None
    week_pattern: dict[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], list[PatternSlot]] = None

    @field_validator("goal_date", "cycle_start")
    @classmethod
    def _iso_date_or_empty(cls, value: str) -> str:
        if value:
            date.fromisoformat(value)  # ValueError → 422 mit Feldname
        return value
