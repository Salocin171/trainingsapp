"""Plan-Import (z. B. 4-Wochen-Block als JSON) und KI-Auftrag für einen Block."""
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .. import db, services
from ..schemas import PlanIn, PromptIn
from ..workouts import summarize

router = APIRouter(prefix="/api/plan")

# Geprüfte Pläne für den Import per Kennung (MCP: Plan nur einmal senden, dann mit preview_id bestätigen)
_previews: dict[str, PlanIn] = {}


@router.post("/preview")
def preview_plan(body: PlanIn):
    warnings: list[str] = []
    workouts, first, last = services.parse_plan(body.plan, body.start, warnings)
    preview_id = uuid4().hex[:8]
    _previews.clear()  # nur die letzte Vorschau merken
    _previews[preview_id] = body
    return {"workouts": [summarize(w) for w in workouts], "start": first.isoformat(), "end": last.isoformat(),
            "existing": len(services.replaceable(first, last)), "warnings": warnings, "preview_id": preview_id}


@router.post("/import")
def import_plan(body: PlanIn):
    return services.import_plan(body.plan, body.start, body.replace)


@router.post("/import/{preview_id}")
def import_previewed_plan(preview_id: str, replace: bool | None = None):
    """Zuletzt geprüften Plan importieren, ohne ihn erneut zu senden."""
    body = _previews.pop(preview_id, None)
    if body is None:
        raise HTTPException(404, "Vorschau nicht mehr vorhanden – Plan erneut prüfen")
    return services.import_plan(body.plan, body.start, body.replace if replace is None else replace)


@router.get("/prompt", response_class=PlainTextResponse)
def plan_prompt_text(start: str = "", weeks: int = 4, notes: str | None = None):
    """KI-Auftrag für einen Block (Text). notes ergänzt bzw. ersetzt die gespeicherte Verfügbarkeit."""
    text, errors, _ = services.plan_brief(start, weeks, notes)
    return text + ("\n\n(Hinweis der App: " + "; ".join(errors) + ")" if errors else "")


@router.post("/prompt")
def plan_prompt_for_ui(body: PromptIn):
    """Für den Import-Dialog: Verfügbarkeit merken und Auftrag samt Kalender-Status liefern."""
    db.save_settings({"availability": body.notes.strip()})
    text, errors, busy_days = services.plan_brief(body.start, body.weeks, body.notes)
    return {"text": text, "errors": errors, "busy_days": busy_days}
