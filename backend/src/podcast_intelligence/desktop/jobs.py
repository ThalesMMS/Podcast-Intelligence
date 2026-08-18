from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
from openai import APIConnectionError, InternalServerError, RateLimitError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from podcast_intelligence.config import Settings
from podcast_intelligence.database import SessionLocal, job_execution_session
from podcast_intelligence.domain.errors import JobCancelledError
from podcast_intelligence.enums import EpisodeStatus, JobStatus, StepStatus
from podcast_intelligence.models import JobDispatch, ProcessingJob, ProcessingStep
from podcast_intelligence.services.imports import enqueue_job_dispatch
from podcast_intelligence.services.pipeline import JobPipeline
from podcast_intelligence.services.providers import build_registry

logger = logging.getLogger(__name__)

_TRANSIENT_ERRORS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    APIConnectionError,
    InternalServerError,
    RateLimitError,
)
_TERMINAL_JOB_STATUSES = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


class DesktopJobRunner:
    """Durable, in-process replacement for Redis, Celery worker and beat.

    The database outbox remains the source of truth. A single polling thread
    claims rows and a bounded executor runs the existing idempotent pipeline.
    Interrupted jobs are made runnable again at the next application launch.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stop = threading.Event()
        self._poller: threading.Thread | None = None
        self._executor = ThreadPoolExecutor(
            max_workers=settings.desktop_job_workers,
            thread_name_prefix="podcast-job",
        )
        self._active: set[uuid.UUID] = set()
        self._active_guard = threading.Lock()

    def start(self) -> None:
        if self._poller is not None:
            return
        self._recover_interrupted_jobs()
        self._poller = threading.Thread(
            target=self._poll_loop,
            name="podcast-job-dispatcher",
            daemon=True,
        )
        self._poller.start()

    def stop(self) -> None:
        self._stop.set()
        if self._poller is not None:
            self._poller.join(timeout=5)
            self._poller = None
        self._executor.shutdown(wait=False, cancel_futures=False)

    def wake(self) -> None:
        """Wake the poller after an import or retry is committed."""

        self._stop.wait(0)

    def _recover_interrupted_jobs(self) -> None:
        with SessionLocal() as session:
            jobs = list(
                session.scalars(
                    select(ProcessingJob)
                    .where(
                        ProcessingJob.status.in_(
                            {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYING}
                        )
                    )
                    .options(selectinload(ProcessingJob.steps))
                )
            )
            for job in jobs:
                if job.status in {JobStatus.RUNNING, JobStatus.RETRYING}:
                    job.status = JobStatus.QUEUED
                    job.episode.status = EpisodeStatus.QUEUED
                    job.completed_at = None
                for step in job.steps:
                    if step.status == StepStatus.RUNNING:
                        step.status = StepStatus.PENDING
                        step.completed_at = None
                        step.error_message = None
                dispatch = enqueue_job_dispatch(session, job.id)
                dispatch.available_at = datetime.now(UTC)
            session.commit()
        if jobs:
            logger.info("desktop_jobs_recovered", count=len(jobs))

    def _poll_loop(self) -> None:
        interval = self.settings.desktop_job_poll_seconds
        while not self._stop.is_set():
            try:
                self._claim_and_submit()
            except Exception:
                logger.exception("Desktop job dispatcher failed")
            self._stop.wait(interval)

    def _claim_and_submit(self) -> None:
        with self._active_guard:
            capacity = max(0, self.settings.desktop_job_workers - len(self._active))
        if capacity <= 0:
            return

        now = datetime.now(UTC)
        claimed: list[uuid.UUID] = []
        with SessionLocal() as session:
            dispatches = list(
                session.scalars(
                    select(JobDispatch)
                    .join(ProcessingJob, ProcessingJob.id == JobDispatch.job_id)
                    .where(
                        JobDispatch.dispatched_at.is_(None),
                        JobDispatch.dead_lettered_at.is_(None),
                        JobDispatch.available_at <= now,
                        ProcessingJob.status.not_in(_TERMINAL_JOB_STATUSES),
                    )
                    .order_by(JobDispatch.available_at, JobDispatch.created_at, JobDispatch.id)
                    .limit(capacity)
                )
            )
            for dispatch in dispatches:
                with self._active_guard:
                    if dispatch.job_id in self._active:
                        continue
                    self._active.add(dispatch.job_id)
                dispatch.dispatched_at = now
                dispatch.attempts += 1
                claimed.append(dispatch.job_id)
            session.commit()

        for job_id in claimed:
            try:
                future = self._executor.submit(self._execute, job_id)
            except RuntimeError:
                self._release_claim(job_id, "Desktop executor rejected the job")
                continue
            future.add_done_callback(lambda result, parsed_id=job_id: self._finished(parsed_id, result))

    def _execute(self, job_id: uuid.UUID) -> None:
        with job_execution_session(job_id) as session:
            if session is None:
                return
            registry = build_registry(self.settings)
            try:
                JobPipeline(session, registry).run(job_id)
            except JobCancelledError:
                return
            except _TRANSIENT_ERRORS as exc:
                self._schedule_retry(job_id, exc)
            except Exception:
                # JobPipeline records the failure and step context transactionally.
                logger.exception("desktop_job_failed", job_id=str(job_id))
            finally:
                registry.http.close()

    def _schedule_retry(self, job_id: uuid.UUID, exc: Exception) -> None:
        with SessionLocal() as session:
            job = session.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.id == job_id)
                .options(selectinload(ProcessingJob.steps))
            )
            if job is None or job.status == JobStatus.CANCELLED:
                return
            options = dict(job.options_json or {})
            retries = int(options.get("_desktop_transient_retries", 0)) + 1
            options["_desktop_transient_retries"] = retries
            job.options_json = options
            if retries > 3:
                dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
                if dispatch is not None:
                    dispatch.dead_lettered_at = datetime.now(UTC)
                    dispatch.last_error = f"{type(exc).__name__}: {str(exc)[:1000]}"
                session.commit()
                logger.error("desktop_job_retries_exhausted", job_id=str(job_id))
                return

            job.status = JobStatus.RETRYING
            job.completed_at = None
            job.episode.status = EpisodeStatus.QUEUED
            if job.current_step:
                for step in job.steps:
                    if step.name == job.current_step and step.status == StepStatus.FAILED:
                        step.status = StepStatus.PENDING
                        step.completed_at = None
                        step.error_message = None
                        break
            dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
            if dispatch is None:
                dispatch = JobDispatch(job_id=job_id)
                session.add(dispatch)
            delay_seconds = min(300, 15 * (2 ** (retries - 1)))
            dispatch.dispatched_at = None
            dispatch.dead_lettered_at = None
            dispatch.available_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
            dispatch.last_error = f"{type(exc).__name__}: {str(exc)[:1000]}"
            session.commit()
        logger.warning("desktop_job_retry_scheduled", job_id=str(job_id))

    def _release_claim(self, job_id: uuid.UUID, error: str) -> None:
        with SessionLocal() as session:
            dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
            if dispatch is not None:
                dispatch.dispatched_at = None
                dispatch.available_at = datetime.now(UTC) + timedelta(seconds=2)
                dispatch.last_error = error
                session.commit()
        with self._active_guard:
            self._active.discard(job_id)

    def _finished(self, job_id: uuid.UUID, future: Future[None]) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("desktop_worker_unhandled_failure", job_id=str(job_id))
        finally:
            with self._active_guard:
                self._active.discard(job_id)
