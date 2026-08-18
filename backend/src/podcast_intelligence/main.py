from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from podcast_intelligence import __version__
from podcast_intelligence.api.router import api_router
from podcast_intelligence.config import get_settings
from podcast_intelligence.database import SessionLocal, create_database_schema
from podcast_intelligence.dependencies import get_registry
from podcast_intelligence.desktop.jobs import DesktopJobRunner
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
    if settings.desktop_mode:
        create_database_schema()
    registry = get_registry()
    with SessionLocal() as session:
        bootstrap_infrastructure(session, settings, registry)

    job_runner: DesktopJobRunner | None = None
    if settings.job_backend == "local":
        job_runner = DesktopJobRunner(settings)
        job_runner.start()
    try:
        yield
    finally:
        if job_runner is not None:
            job_runner.stop()
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
    allow_origin_regex=(
        r"^(?:tauri://localhost|https?://(?:tauri\.localhost|localhost|127\.0\.0\.1)(?::\d+)?)$"
        if settings.desktop_mode
        else None
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Desktop-Token"],
)
app.include_router(api_router)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.middleware("http")
async def desktop_loopback_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Protect the loopback API from unrelated local processes.

    Upload and playback URLs carry short-lived HMAC tokens and therefore do not
    require the session token. Health endpoints remain readable so the Tauri
    host can wait for startup without exposing user data.
    """

    if not settings.desktop_mode or request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path.startswith("/health/") or path.startswith("/v1/desktop-storage/"):
        return await call_next(request)
    supplied = request.headers.get("X-Desktop-Token", "")
    expected = settings.desktop_api_token or ""
    if not expected or not hmac.compare_digest(supplied, expected):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "desktop_auth_required", "message": "Desktop session token required"},
        )
    return await call_next(request)


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
    if settings.job_backend == "celery":
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
        client.ping()
        checks["redis"] = "ok"
    else:
        checks["job_runner"] = "local"
    return HealthResponse(status="ready", version=__version__, checks=checks)
