from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from podcast_intelligence import __version__
from podcast_intelligence.api.router import api_router
from podcast_intelligence.config import get_settings
from podcast_intelligence.database import SessionLocal
from podcast_intelligence.dependencies import get_registry
from podcast_intelligence.domain.errors import (
    ConflictError,
    NotFoundError,
    PodcastIntelligenceError,
)
from podcast_intelligence.logging import configure_logging
from podcast_intelligence.schemas import ErrorResponse, HealthResponse
from podcast_intelligence.services.bootstrap import bootstrap_infrastructure

settings = get_settings()
configure_logging(settings.app_debug)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    registry = get_registry()
    with SessionLocal() as session:
        bootstrap_infrastructure(session, settings, registry)
    yield
    registry.http.close()


app = FastAPI(
    title="Podcast Intelligence API",
    version=__version__,
    description="Podcast ingestion, diarized transcription, structured summaries and grounded RAG.",
    default_response_class=JSONResponse,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "imports", "description": "Upload, import and pipeline jobs."},
        {"name": "episodes", "description": "Episode knowledge artifacts."},
        {"name": "conversations", "description": "Grounded podcast chat."},
        {"name": "system", "description": "Search and provider introspection."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(api_router)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.exception_handler(PodcastIntelligenceError)
def handle_domain_error(_: Request, exc: PodcastIntelligenceError) -> JSONResponse:
    code = status.HTTP_400_BAD_REQUEST
    if isinstance(exc, NotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ConflictError):
        code = status.HTTP_409_CONFLICT
    payload = ErrorResponse(code=exc.code, message=str(exc))
    return JSONResponse(status_code=code, content=payload.model_dump(mode="json"))


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
def live() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
def ready() -> HealthResponse:
    checks: dict[str, str] = {}
    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    get_registry().object_store.health()
    checks["object_store"] = "ok"
    client = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
    client.ping()
    checks["redis"] = "ok"
    return HealthResponse(status="ready", version=__version__, checks=checks)
