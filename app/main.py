"""Web-Server (FastAPI): App zusammenbauen. Start: ./Trainingsapp.command oder
    .venv/bin/uvicorn app.main:app --reload --port 8765

Die Endpunkte stehen in app/routes/ (ein Modul je Bereich), die Abläufe in app/services.py.
"""
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routes import plan, races, system, training, workouts
from .services import ExternalError, ServiceError

app = FastAPI(title="Trainingsapp")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
for module in (workouts, plan, training, races, system):
    app.include_router(module.router)


@app.exception_handler(ServiceError)
def _bad_request(_: Request, e: ServiceError):
    return JSONResponse({"detail": str(e)}, status_code=400)


@app.exception_handler(ExternalError)
def _bad_gateway(_: Request, e: ExternalError):
    return JSONResponse({"detail": str(e)}, status_code=502)


@app.middleware("http")
async def always_fresh_ui(request, call_next):
    """Oberfläche bei jedem Laden neu prüfen (ETag), damit der Browser nach Updates keine alten Skripte nutzt."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")
