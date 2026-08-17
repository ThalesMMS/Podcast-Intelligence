from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any

import httpx
from botocore.exceptions import EndpointConnectionError
from openai import APIConnectionError, InternalServerError, RateLimitError
from sqlalchemy import Select, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from podcast_intelligence.config import Settings, get_settings
from podcast_intelligence.database import SessionLocal, job_execution_session
from podcast_intelligence.domain.errors import JobCancelledError
from podcast_intelligence.enums import JobStatus, StepStatus
from podcast_intelligence.models import JobDispatch, ProcessingJob, ProcessingStep
from podcast_intelligence.services.pipeline import JobPipeline
from podcast_intelligence.services.providers import build_registry
from podcast_intelligence.worker.celery_app import celery_app

_TRANSIENT_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    EndpointConnectionError,
    APIConnectionError,
    InternalServerError,
    RateLimitError,
)
_DATABASE_TRANSIENT_ERRORS = (OperationalError, SQLAlchemyTimeoutError)
_DISPATCH_BATCH_SIZE = 100


def _run_process_job(
    self: Any,
    job_id: str,
    parsed_id: uuid.UUID,
    settings: Settings,
) -> dict[str, str]:
    with job_execution_session(parsed_id) as session:
        if session is None:
            return {"job_id": job_id, "status": "already_running"}

        registry = build_registry(settings)
        try:
            JobPipeline(session, registry).run(parsed_id)
            return {"job_id": job_id, "status": "completed"}
        except JobCancelledError:
            return {"job_id": job_id, "status": "cancelled"}
        except _TRANSIENT_ERRORS as exc:
            session.rollback()
            job = session.get(ProcessingJob, parsed_id)
            if job is not None and self.request.retries < self.max_retries:
                job.status = JobStatus.RETRYING
                if job.current_step:
                    step = session.scalar(
                        select(ProcessingStep).where(
                            ProcessingStep.job_id == parsed_id,
                            ProcessingStep.name == job.current_step,
                        )
                    )
                    if step is not None and step.status == StepStatus.FAILED:
                        step.status = StepStatus.PENDING
                session.commit()
                countdown = min(300, 15 * (2**self.request.retries))
                raise self.retry(exc=exc, countdown=countdown) from exc
            raise
        finally:
            registry.http.close()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True, max_retries=3, name="podcast_intelligence.process_job"
)
def process_job(self: Any, job_id: str) -> dict[str, str]:
    parsed_id = uuid.UUID(job_id)
    settings = get_settings()
    try:
        return _run_process_job(self, job_id, parsed_id, settings)
    except _DATABASE_TRANSIENT_ERRORS as exc:
        countdown = min(300, 15 * (2**self.request.retries))
        raise self.retry(exc=exc, countdown=countdown) from exc


def _pending_dispatch_statement(now: datetime, batch_size: int) -> Select[tuple[JobDispatch]]:
    return (
        select(JobDispatch)
        .where(
            JobDispatch.dispatched_at.is_(None),
            JobDispatch.dead_lettered_at.is_(None),
            JobDispatch.available_at <= now,
        )
        .order_by(JobDispatch.available_at, JobDispatch.created_at, JobDispatch.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )


@celery_app.task(name="podcast_intelligence.dispatch_pending_jobs")  # type: ignore[untyped-decorator]
def dispatch_pending_jobs(batch_size: int = _DISPATCH_BATCH_SIZE) -> dict[str, int]:
    """Publish committed outbox rows; duplicate publication is safe by job lock."""
    published = 0
    failed = 0
    dead_lettered = 0
    now = datetime.now(UTC)
    settings = get_settings()
    max_attempts = settings.dispatch_max_attempts
    started_at = monotonic()
    dispatch_limit = max(1, min(batch_size, 500))
    with SessionLocal() as session:
        for _ in range(dispatch_limit):
            if monotonic() - started_at >= settings.dispatch_run_time_budget_seconds:
                break
            dispatch = session.scalar(_pending_dispatch_statement(now, 1))
            if dispatch is None:
                break
            dispatch.attempts += 1
            try:
                process_job.delay(str(dispatch.job_id))
            except Exception as exc:
                failed += 1
                dispatch.last_error = f"Broker publish failed ({type(exc).__name__})"
                if dispatch.attempts >= max_attempts:
                    dead_lettered += 1
                    dispatch.dead_lettered_at = datetime.now(UTC)
                else:
                    delay_seconds = min(300, 5 * (2 ** min(dispatch.attempts - 1, 6)))
                    dispatch.available_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
            else:
                published += 1
                dispatch.dispatched_at = datetime.now(UTC)
                dispatch.last_error = None
            session.commit()
    return {"published": published, "failed": failed, "dead_lettered": dead_lettered}
