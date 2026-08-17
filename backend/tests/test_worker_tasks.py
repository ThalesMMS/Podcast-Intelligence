from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from threading import Event, Thread
from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from podcast_intelligence import database
from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.config import Settings
from podcast_intelligence.enums import StepStatus
from podcast_intelligence.services.pipeline import JobPipeline
from podcast_intelligence.worker import tasks


def test_failed_advisory_unlock_invalidates_connection(monkeypatch: MonkeyPatch) -> None:
    connection = SimpleNamespace()
    connection.invalidated = False
    connection.scalar = lambda *_args, **_kwargs: True
    connection.commit = lambda: None
    connection.invalidate = lambda: setattr(connection, "invalidated", True)

    def execute(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("simulated unlock failure")

    connection.execute = execute

    class _ConnectionContext:
        def __enter__(self) -> SimpleNamespace:
            return connection

        def __exit__(self, *_args: object) -> None:
            return None

    fake_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        connect=lambda: _ConnectionContext(),
    )

    class _SessionContext:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _SessionContext:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(database, "engine", fake_engine)
    monkeypatch.setattr(database, "Session", _SessionContext)

    with database.job_execution_session(uuid.uuid4()) as session:
        assert session is not None

    assert connection.invalidated


def test_postgres_advisory_lock_contention_yields_no_session(
    monkeypatch: MonkeyPatch,
) -> None:
    connection = SimpleNamespace()
    connection.scalar = lambda *_args, **_kwargs: False
    connection.commit = lambda: None

    def unexpected_execute(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("an unowned advisory lock must not be released")

    connection.execute = unexpected_execute

    class _ConnectionContext:
        def __enter__(self) -> SimpleNamespace:
            return connection

        def __exit__(self, *_args: object) -> None:
            return None

    fake_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        connect=lambda: _ConnectionContext(),
    )
    monkeypatch.setattr(database, "engine", fake_engine)

    with database.job_execution_session(uuid.uuid4()) as session:
        assert session is None


def test_duplicate_worker_exits_without_building_providers(monkeypatch: MonkeyPatch) -> None:
    started = Event()
    release = Event()
    results: list[dict[str, str]] = []
    registry_builds = 0

    class _BlockingPipeline:
        def __init__(self, _session: object, _registry: object) -> None:
            pass

        def run(self, _job_id: uuid.UUID) -> None:
            started.set()
            assert release.wait(timeout=5)

    def build_registry(_settings: Settings) -> SimpleNamespace:
        nonlocal registry_builds
        registry_builds += 1
        return SimpleNamespace(http=SafeHTTPClient(Settings()))

    monkeypatch.setattr(tasks, "build_registry", build_registry)
    monkeypatch.setattr(tasks, "JobPipeline", _BlockingPipeline)
    job_id = uuid.uuid4()
    first = Thread(target=lambda: results.append(tasks.process_job.run(str(job_id))))

    first.start()
    assert started.wait(timeout=5)
    duplicate = tasks.process_job.run(str(job_id))
    release.set()
    first.join(timeout=5)
    assert not first.is_alive(), "worker thread did not finish in time"

    assert duplicate == {"job_id": str(job_id), "status": "already_running"}
    assert results == [{"job_id": str(job_id), "status": "completed"}]
    assert registry_builds == 1


def test_job_can_be_redelivered_after_worker_failure(monkeypatch: MonkeyPatch) -> None:
    attempts = 0

    class _FailOncePipeline:
        def __init__(self, _session: object, _registry: object) -> None:
            pass

        def run(self, _job_id: uuid.UUID) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("simulated worker loss")

    monkeypatch.setattr(
        tasks,
        "build_registry",
        lambda _settings: SimpleNamespace(http=SafeHTTPClient(Settings())),
    )
    monkeypatch.setattr(tasks, "JobPipeline", _FailOncePipeline)
    job_id = uuid.uuid4()

    with pytest.raises(RuntimeError, match="simulated worker loss"):
        tasks.process_job.run(str(job_id))
    result = tasks.process_job.run(str(job_id))

    assert result == {"job_id": str(job_id), "status": "completed"}
    assert attempts == 2


def test_database_pool_timeout_retries_without_building_providers(
    monkeypatch: MonkeyPatch,
) -> None:
    @contextmanager
    def unavailable_session(_job_id: uuid.UUID) -> Generator[None, None, None]:
        raise SQLAlchemyTimeoutError("simulated pool exhaustion")
        yield None

    retried = RuntimeError("retry scheduled")

    def retry(*, exc: BaseException, countdown: int) -> None:
        assert isinstance(exc, SQLAlchemyTimeoutError)
        assert countdown == 15
        raise retried

    monkeypatch.setattr(tasks, "job_execution_session", unavailable_session)
    monkeypatch.setattr(tasks.process_job, "retry", retry)
    monkeypatch.setattr(
        tasks,
        "build_registry",
        lambda _settings: (_ for _ in ()).throw(
            AssertionError("providers must not be built without a database connection")
        ),
    )

    with pytest.raises(RuntimeError, match="retry scheduled"):
        tasks.process_job.run(str(uuid.uuid4()))


def test_completed_step_is_not_executed_again() -> None:
    step = SimpleNamespace(status=StepStatus.COMPLETED)
    session = SimpleNamespace(scalar=lambda _statement: step)
    pipeline = object.__new__(JobPipeline)
    pipeline.session = session
    job = SimpleNamespace(id=uuid.uuid4())
    handler_called = False

    def handler(_job: object) -> dict[str, object]:
        nonlocal handler_called
        handler_called = True
        return {}

    pipeline._execute_step(job, "transcribe", handler)  # type: ignore[arg-type]

    assert not handler_called
