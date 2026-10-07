from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .db import Base, engine
from .routes import admin, auth, documents, events
from .services.errors import ServiceError

settings = get_settings()
logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')

_public_docs = settings.env != "production"
app = FastAPI(title=settings.app_name, version=__version__, redoc_url=None,
              docs_url="/api/docs" if _public_docs else None,
              openapi_url="/api/openapi.json" if _public_docs else None)

if settings.env != "production":
    # Production schema is managed by Alembic (`alembic upgrade head` in the migrate job).
    Base.metadata.create_all(bind=engine)


@app.exception_handler(ServiceError)
async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse({"error": exc.as_dict()}, status_code=exc.status)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(documents.router)
app.include_router(events.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "engine_mode": settings.engine_mode}
