from __future__ import annotations

import hashlib
import uuid
from _thread import LockType
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from threading import Lock

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from podcast_intelligence.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)

_active_local_jobs: set[uuid.UUID] = set()
_active_local_jobs_guard = Lock()


@dataclass(slots=True)
class _LocalSummaryLock:
    lock: LockType = field(default_factory=Lock)
    users: int = 0


_active_local_summaries: dict[uuid.UUID, _LocalSummaryLock] = {}
_active_local_summaries_guard = Lock()


def _job_lock_key(job_id: uuid.UUID) -> int:
    return int.from_bytes(job_id.bytes[:8], byteorder="big", signed=True)


def _summary_lock_key(transcript_id: uuid.UUID) -> int:
    digest = hashlib.blake2b(
        b"summary-generation:" + transcript_id.bytes,
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def summary_generation_transaction(
    session: Session,
    transcript_id: uuid.UUID,
) -> Generator[None, None, None]:
    """Serialize one transcript's summary generation and own its transaction.

    The supplied session must have no unrelated pending or dirty state because
    this context commits or rolls back the caller's entire transaction.
    """
    local_entry = None
    local_acquired = False
    try:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": _summary_lock_key(transcript_id)},
            )
        else:
            with _active_local_summaries_guard:
                local_entry = _active_local_summaries.setdefault(
                    transcript_id,
                    _LocalSummaryLock(),
                )
                local_entry.users += 1
            local_acquired = local_entry.lock.acquire()
        yield
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        if local_entry is not None:
            if local_acquired:
                local_entry.lock.release()
            with _active_local_summaries_guard:
                local_entry.users -= 1
                if local_entry.users == 0:
                    _active_local_summaries.pop(transcript_id, None)


@contextmanager
def job_execution_session(job_id: uuid.UUID) -> Generator[Session | None, None, None]:
    """Yield a session only when this process owns the job execution lock."""
    if engine.dialect.name != "postgresql":
        with _active_local_jobs_guard:
            acquired = job_id not in _active_local_jobs
            if acquired:
                _active_local_jobs.add(job_id)
        if not acquired:
            yield None
            return
        try:
            with SessionLocal() as session:
                yield session
        finally:
            with _active_local_jobs_guard:
                _active_local_jobs.discard(job_id)
        return

    lock_key = _job_lock_key(job_id)
    with engine.connect() as connection:
        acquired = bool(
            connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": lock_key},
            )
        )
        connection.commit()
        if not acquired:
            yield None
            return

        try:
            with Session(
                bind=connection,
                expire_on_commit=False,
                autoflush=False,
            ) as session:
                yield session
        finally:
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": lock_key},
                )
                connection.commit()
            except SQLAlchemyError:
                with suppress(SQLAlchemyError):
                    connection.invalidate()


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
