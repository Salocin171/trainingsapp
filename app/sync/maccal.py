"""Kalender-App von macOS: geplante Workouts als ganztägige Termine in einen Kalender schreiben.

Funktioniert mit jedem Kalender, der in der Kalender-App eingerichtet ist (iCloud, Outlook/Exchange …) –
macOS synchronisiert die Termine dann selbst zum Konto und aufs iPhone. Keine Anmeldung, keine Cloud-Einrichtung;
beim ersten Mal fragt macOS, ob die Trainingsapp die Kalender-App steuern darf (Datenschutz → Automation).
Gesteuert wird per AppleScript (osascript). Der Kalender wird über seinen Namen gewählt (Einstellung "mac_calendar").
"""
import subprocess
import sys
import time
from datetime import date

from ..workouts import estimate_tss, step_target, total_duration

SPORT_DE = {"swim": "Schwimmen", "ride": "Radfahren", "run": "Laufen", "strength": "Stabi / Kraft",
            "mobility": "Dehnen / Yoga", "other": "Sonstiges"}
MAX_TITLE_NAME = 30  # längere Programmnamen stehen nur in der Beschreibung
KIND_DE = {"warmup": "Einwärmen", "interval": "Intervall", "recovery": "Erholung", "steady": "Konstant",
           "cooldown": "Ausfahren"}
DENIED_HINT = ("macOS erlaubt der Trainingsapp keinen Zugriff auf die Kalender-App. Systemeinstellungen → "
               "Datenschutz & Sicherheit → Automation → beim Programm der Trainingsapp (Terminal bzw. python) "
               "„Kalender“ einschalten.")

# --- Text der Termine -----------------------------------------------------------

def _pace(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"


def target_text(workout: dict, step: dict, settings: dict) -> str:
    """Zielbereich eines Schritts in Watt / Pace / Puls – wie die Anzeige im Editor."""
    low, high = float(step.get("low") or 0), float(step.get("high") or step.get("low") or 0)
    sport, target = workout.get("sport"), step_target(workout, step)
    if not (low or high) or sport in ("strength", "mobility"):
        return ""
    if target == "power":
        lo, hi, unit = round(settings["ftp"] * low / 100), round(settings["ftp"] * high / 100), " W"
    elif target == "hr":
        lthr = settings["lthr_ride"] if sport == "ride" else settings["lthr_run"]
        lo, hi, unit = round(lthr * low / 100), round(lthr * high / 100), " bpm"
    else:  # mehr % = schneller
        base = settings["css"] if sport == "swim" else settings["threshold_pace"]
        lo, hi = _pace(base / (low / 100)), _pace(base / (high / 100))
        unit = " /100 m" if sport == "swim" else " /km"
    return f"{lo}{unit}" if lo == hi else f"{lo}–{hi}{unit}"


def _step_lines(workout: dict, steps: list[dict], settings: dict, indent: str = "") -> list[str]:
    lines = []
    for s in steps:
        if s.get("kind") == "repeat":
            lines.append(f"{indent}{s['count']}×")
            lines += _step_lines(workout, s.get("steps", []), settings, indent + "   ")
        else:
            minutes = s["duration"] / 60
            duration = f"{minutes:g} min" if minutes >= 1 else f"{s['duration']} s"
            target = target_text(workout, s, settings)
            lines.append(f"{indent}• {duration} {KIND_DE.get(s['kind'], s['kind'])}" + (f" – {target}" if target else ""))
    return lines


def _short_name(name: str) -> str:
    """Programm für den Titel: ohne Klammerzusatz, wenn nötig nur der Teil vor dem Doppelpunkt; zu lang → leer."""
    short = name.split(" (")[0].strip()
    if len(short) > MAX_TITLE_NAME:
        short = short.split(": ")[0]
    return short if len(short) <= MAX_TITLE_NAME else ""


def event_text(workout: dict, settings: dict) -> tuple[str, str]:
    """(Titel, Beschreibung): Titel „Sportart – Programm“; Beschreibung mit vollem Namen, Schritten in absoluten
    Werten, Dauer und TSS."""
    minutes = round(total_duration(workout.get("steps", [])) / 60)
    duration = f"{minutes // 60}:{minutes % 60:02d} h" if minutes >= 60 else f"{minutes} min"
    sport = SPORT_DE.get(workout.get("sport"), SPORT_DE["other"])
    name = workout.get("name", "Workout")
    short = _short_name(name)
    description = "\n".join(filter(None, [
        name if short != name else "",  # im Titel gekürzt → hier vollständig
        workout.get("description", ""),
        "",
        *_step_lines(workout, workout.get("steps", []), settings),
        "",
        f"Geplant mit der Trainingsapp · {duration} · {round(estimate_tss(workout))} TSS",
    ])).strip()
    return (f"{sport} – {short}" if short and short != sport else sport), description


# --- AppleScript --------------------------------------------------------------

_PUSH = '''on run argv
	set {calName, oldCal, theUid, theTitle, theDesc, y, m, d} to argv
	set dt to current date
	set day of dt to 1
	set year of dt to (y as integer)
	set month of dt to (m as integer)
	set day of dt to (d as integer)
	set time of dt to 0
	tell application "Calendar"
		set c to first calendar whose name is calName
		if theUid is not "" then
			if oldCal is not calName then
				try
					delete (every event of (first calendar whose name is oldCal) whose uid is theUid)
				end try
			else
				set found to (every event of c whose uid is theUid)
				if (count of found) > 0 then
					set e to item 1 of found
					-- Datum nie per „set start/end date“ ändern: bei ganztägigen Terminen wird das Ende dann als
					-- inklusiv gelesen (→ 2 Tage) bzw. ein späterer Start abgelehnt. Gleicher Tag → nur Text,
					-- sonst (verschoben oder schon kaputt) löschen und unten neu anlegen.
					if (allday event of e) and (start date of e) = dt and (end date of e) < dt + 1 * days then
						set summary of e to theTitle
						set description of e to theDesc
						return uid of e
					end if
					delete e
				end if
			end if
		end if
		-- „ganztägig“ zuerst und Ende = Start: sonst entsteht erst ein 0–24-Uhr-Termin, den die Kalender-App beim
		-- Umwandeln in ganztägig auf zwei Tage ausdehnt
		set e to make new event at end of events of c with properties {allday event:true, summary:theTitle, description:theDesc, start date:dt, end date:dt}
		return uid of e
	end tell
end run'''

_REMOVE = '''on run argv
	set {calName, theUid} to argv
	tell application "Calendar"
		try
			delete (every event of (first calendar whose name is calName) whose uid is theUid)
		end try
	end tell
end run'''

_LIST = '''tell application "Calendar"
	set out to ""
	set ns to name of every calendar
	set ws to writable of every calendar
	repeat with i from 1 to count of ns
		set out to out & (item i of ns) & tab & (item i of ws) & linefeed
	end repeat
	return out
end tell'''


# Nach fehlender Berechtigung bzw. Zeitüberschreitung eine Weile nicht erneut warten – sonst hinge jedes Speichern
# eines Workouts (Auto-Sync) bis zur Zeitüberschreitung. Die Kalenderauswahl in den Einstellungen fragt trotzdem neu.
PAUSE_SECONDS = 600
_blocked_until = 0.0
_blocked_reason = ""


def _block(reason: str) -> RuntimeError:
    global _blocked_until, _blocked_reason
    _blocked_until, _blocked_reason = time.monotonic() + PAUSE_SECONDS, reason
    return RuntimeError(reason)


def _osascript(script: str, *args: str, timeout: int = 60, retry: bool = False) -> str:
    if sys.platform != "darwin":
        raise RuntimeError("Die Kalender-App gibt es nur auf dem Mac.")
    if not retry and time.monotonic() < _blocked_until:
        raise RuntimeError(_blocked_reason)
    try:
        r = subprocess.run(["osascript", "-e", script, *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Typisch beim ersten Mal: macOS zeigt „… möchte „Kalender“ steuern“ und wartet auf eine Antwort
        raise _block("Die Kalender-App antwortet nicht. Wartet ein macOS-Dialog „… möchte „Kalender“ steuern“? "
                     "Mit OK bestätigen und die Einstellungen der Trainingsapp neu öffnen. " + DENIED_HINT) from None
    if r.returncode:
        err = r.stderr.strip()
        if "-1743" in err or "not allowed" in err.lower() or "nicht erlaubt" in err.lower():
            raise _block(DENIED_HINT)
        if "-1719" in err or "-1728" in err:  # Objekt nicht gefunden
            raise RuntimeError("Kalender nicht gefunden – in den Einstellungen einen Kalender auswählen.")
        raise RuntimeError(f"Kalender-App: {err or 'unbekannter Fehler'}")
    return r.stdout.strip()


def calendars() -> list[dict]:
    """Alle Kalender der Kalender-App: [{"name", "writable"}] (für die Auswahl in den Einstellungen)."""
    global _blocked_until
    out = []
    lines = _osascript(_LIST, retry=True).splitlines()  # bewusst neu fragen: löst ggf. den macOS-Dialog aus
    _blocked_until = 0.0  # Zugriff klappt wieder
    for line in lines:
        name, _, writable = line.rpartition("\t")
        if name:
            out.append({"name": name, "writable": writable.strip() == "true"})
    return out


def _calendar(settings: dict) -> str:
    name = settings.get("mac_calendar") or ""
    if not name:
        raise RuntimeError("Kein Kalender gewählt – in den Einstellungen unter „Kalender“ auswählen.")
    return name


def is_connected(settings: dict) -> bool:
    # während einer Sperrpause gilt der Kalender als nicht verbunden → Auto-Sync überspringt ihn statt zu hängen
    return sys.platform == "darwin" and bool(settings.get("mac_calendar")) and time.monotonic() >= _blocked_until


def push(workout: dict, settings: dict) -> dict:
    cal = _calendar(settings)
    existing = (workout.get("sync") or {}).get("calendar") or {}
    title, description = event_text(workout, settings)
    day = date.fromisoformat(workout["date"])
    uid = _osascript(_PUSH, cal, existing.get("calendar") or cal, existing.get("uid") or "", title, description,
                     str(day.year), str(day.month), str(day.day))
    return {"uid": uid, "calendar": cal}


def remove(workout: dict) -> None:
    info = (workout.get("sync") or {}).get("calendar") or {}
    if info.get("uid") and sys.platform == "darwin":
        _osascript(_REMOVE, info.get("calendar") or "", info["uid"])
