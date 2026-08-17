from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from pytest import MonkeyPatch, fixture
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from podcast_intelligence.config import Settings
from podcast_intelligence.database import Base
from podcast_intelligence.enums import JobStatus, SourceType
from podcast_intelligence.models import JobDispatch, ProcessingJob
from podcast_intelligence.schemas import ImportRequest, ImportSourceInput
from podcast_intelligence.services.imports import ImportService, enqueue_job_dispatch
from podcast_intelligence.worker import tasks
from podcast_intelligence.worker.celery_app import celery_app


@fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    finally:
        engine.dispose()


def _create_import(session: Session, workspace_id: uuid.UUID) -> uuid.UUID:
    request = ImportRequest(
        source=ImportSourceInput(
            type=SourceType.DIRECT_URL,
            url="https://example.com/episode.mp3",
        )
    )
    response = ImportService(session, SimpleNamespace(), Settings()).create_import(
        workspace_id, request
    )
    return response.job_id


def test_import_commits_pending_dispatch_with_job(
    session_factory: sessionmaker[Session],
) -> None:
    workspace_id = uuid.uuid4()
    with session_factory() as session:
        job_id = _create_import(session, workspace_id)
        dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
        job = session.get(ProcessingJob, job_id)

        assert job is not None
        assert job.status == JobStatus.QUEUED
        assert dispatch is not None
        assert dispatch.dispatched_at is None
        assert dispatch.attempts == 0


def test_enqueue_resets_existing_dispatch_for_retry(
    session_factory: sessionmaker[Session],
) -> None:
    workspace_id = uuid.uuid4()
    with session_factory() as session:
        job_id = _create_import(session, workspace_id)
        dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
        assert dispatch is not None
        dispatch.dispatched_at = datetime.now(UTC)
        dispatch.dead_lettered_at = datetime.now(UTC)
        dispatch.last_error = "old failure"
        dispatch.attempts = 4
        session.commit()

        enqueue_job_dispatch(session, job_id)
        session.commit()

        assert dispatch.dispatched_at is None
        assert dispatch.dead_lettered_at is None
        assert dispatch.last_error is None
        assert dispatch.attempts == 0


def test_dispatcher_retries_broker_failure_then_marks_published(
    monkeypatch: MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    workspace_id = uuid.uuid4()
    with session_factory() as session:
        job_id = _create_import(session, workspace_id)

    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        tasks.process_job,
        "delay",
        lambda _job_id: (_ for _ in ()).throw(
            ConnectionError("redis://operator:secret@broker:6379/0 unavailable")
        ),
    )

    first = tasks.dispatch_pending_jobs.run()

    assert first == {"published": 0, "failed": 1, "dead_lettered": 0}
    with session_factory() as session:
        dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
        assert dispatch is not None
        assert dispatch.dispatched_at is None
        assert dispatch.attempts == 1
        assert dispatch.last_error == "Broker publish failed (ConnectionError)"
        assert "secret" not in dispatch.last_error
        dispatch.available_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    published: list[str] = []
    monkeypatch.setattr(tasks.process_job, "delay", published.append)

    second = tasks.dispatch_pending_jobs.run()

    assert second == {"published": 1, "failed": 0, "dead_lettered": 0}
    assert published == [str(job_id)]
    with session_factory() as session:
        dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
        assert dispatch is not None
        assert dispatch.dispatched_at is not None
        assert dispatch.attempts == 2
        assert dispatch.last_error is None


def test_dispatcher_dead_letters_after_configured_attempt_limit(
    monkeypatch: MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    workspace_id = uuid.uuid4()
    with session_factory() as session:
        job_id = _create_import(session, workspace_id)
        dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
        assert dispatch is not None
        dispatch.attempts = 1
        session.commit()

    attempts: list[str] = []

    def fail_publication(job_id_value: str) -> None:
        attempts.append(job_id_value)
        raise ConnectionError("permanent broker rejection")

    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(dispatch_max_attempts=2),
    )
    monkeypatch.setattr(tasks.process_job, "delay", fail_publication)

    result = tasks.dispatch_pending_jobs.run()
    repeated = tasks.dispatch_pending_jobs.run()

    assert result == {"published": 0, "failed": 1, "dead_lettered": 1}
    assert repeated == {"published": 0, "failed": 0, "dead_lettered": 0}
    assert attempts == [str(job_id)]
    with session_factory() as session:
        dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
        assert dispatch is not None
        assert dispatch.dispatched_at is None
        assert dispatch.dead_lettered_at is not None
        assert dispatch.attempts == 2
        assert dispatch.last_error == "Broker publish failed (ConnectionError)"


def test_dispatcher_leaves_unprocessed_rows_for_next_beat_after_time_budget(
    monkeypatch: MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    workspace_id = uuid.uuid4()
    with session_factory() as session:
        job_ids = {
            _create_import(session, workspace_id),
            _create_import(session, workspace_id),
        }

    published: list[str] = []
    clock = iter([0.0, 0.0, 31.0])
    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: Settings(dispatch_run_time_budget_seconds=30.0),
    )
    monkeypatch.setattr(tasks, "monotonic", lambda: next(clock))
    monkeypatch.setattr(tasks.process_job, "delay", published.append)

    result = tasks.dispatch_pending_jobs.run()

    assert result == {"published": 1, "failed": 0, "dead_lettered": 0}
    assert len(published) == 1
    assert uuid.UUID(published[0]) in job_ids
    with session_factory() as session:
        dispatches = list(
            session.scalars(select(JobDispatch).where(JobDispatch.job_id.in_(job_ids)))
        )
        assert sum(dispatch.dispatched_at is not None for dispatch in dispatches) == 1
        assert sum(dispatch.dispatched_at is None for dispatch in dispatches) == 1
        assert sum(dispatch.attempts for dispatch in dispatches) == 1


def test_dispatcher_selects_and_commits_one_row_at_a_time(
    monkeypatch: MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    workspace_id = uuid.uuid4()
    with session_factory() as session:
        job_ids = [
            _create_import(session, workspace_id),
            _create_import(session, workspace_id),
        ]

    selected_limits: list[int] = []
    commits: list[int] = []
    published: list[str] = []
    original_statement = tasks._pending_dispatch_statement
    original_commit = Session.commit

    def record_statement(now: datetime, batch_size: int):
        selected_limits.append(batch_size)
        return original_statement(now, batch_size)

    def record_commit(session: Session) -> None:
        commits.append(id(session))
        original_commit(session)

    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(tasks, "_pending_dispatch_statement", record_statement)
    monkeypatch.setattr(tasks.process_job, "delay", published.append)
    monkeypatch.setattr(Session, "commit", record_commit)

    result = tasks.dispatch_pending_jobs.run(batch_size=2)

    assert result == {"published": 2, "failed": 0, "dead_lettered": 0}
    assert selected_limits == [1, 1]
    assert len(commits) == 2
    assert set(published) == {str(job_id) for job_id in job_ids}


def test_dispatch_query_uses_skip_locked_on_postgresql() -> None:
    statement = tasks._pending_dispatch_statement(datetime.now(UTC), 10)

    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "job_dispatches.dead_lettered_at IS NULL" in sql


def test_pending_dispatch_model_index_matches_dead_letter_migration() -> None:
    pending_index = next(
        index for index in JobDispatch.__table__.indexes if index.name == "ix_job_dispatch_pending"
    )

    assert [column.name for column in pending_index.columns] == [
        "dispatched_at",
        "dead_lettered_at",
        "available_at",
    ]


def test_dispatch_job_id_unique_constraint_avoids_redundant_index() -> None:
    unique_constraint = next(
        constraint
        for constraint in JobDispatch.__table__.constraints
        if constraint.name == "uq_job_dispatch_job"
    )

    assert [column.name for column in unique_constraint.columns] == ["job_id"]
    assert not any(
        index.name == "ix_job_dispatches_job_id" for index in JobDispatch.__table__.indexes
    )


def test_latest_job_model_index_matches_query_order() -> None:
    latest_index = next(
        index for index in ProcessingJob.__table__.indexes if index.name == "ix_job_episode_created"
    )

    assert [column.name for column in latest_index.columns] == [
        "episode_id",
        "created_at",
        "updated_at",
    ]


def test_celery_producer_publish_retries_and_timeouts_are_bounded() -> None:
    transport_options = celery_app.conf.broker_transport_options
    retry_policy = celery_app.conf.task_publish_retry_policy

    assert transport_options["socket_connect_timeout"] == 5.0
    assert transport_options["socket_timeout"] == 5.0
    assert celery_app.conf.task_publish_retry is True
    assert retry_policy == {
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 0.5,
    }
