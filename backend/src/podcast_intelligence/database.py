from __future__ import annotations

import hashlib
import os
import time
import uuid
from _thread import LockType
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import BinaryIO

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from podcast_intelligence.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args: dict[str, object] = {}
if _is_sqlite:
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()


_active_local_jobs: set[uuid.UUID] = set()
_active_local_jobs_guard = Lock()


@dataclass(slots=True)
class _LocalSummaryLock:
    lock: LockType = field(default_factory=Lock)
    users: int = 0


_active_local_summaries: dict[uuid.UUID, _LocalSummaryLock] = {}
_active_local_summaries_guard = Lock()


def _acquire_desktop_named_file_lock(name: str) -> BinaryIO | None:
    if not settings.desktop_mode:
        return None
    lock_dir = Path(settings.desktop_data_dir) / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    handle = (lock_dir / f"{name}.lock").open("a+b")
    if handle.seek(0, os.SEEK_END) == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.05)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _release_desktop_file_lock(handle: BinaryIO | None) -> None:
    if handle is None:
        return
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def create_database_schema() -> None:
    """Create the local schema for a fresh desktop database.

    Server deployments continue to use Alembic. Desktop builds deliberately use
    SQLAlchemy metadata because the bundled SQLite database is private to the
    installed application and starts empty on first launch.
    """

    # Importing models registers every table on Base.metadata.
    from podcast_intelligence import models as _models  # noqa: F401

    Base.metadata.create_all(bind=engine)


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
    """Serialize one transcript's summary generation and own its transaction."""

    local_entry = None
    local_acquired = False
    file_lock: BinaryIO | None = None
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
            file_lock = _acquire_desktop_named_file_lock(f"summary-{transcript_id}")
        yield
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        _release_desktop_file_lock(file_lock)
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
        job_file_lock: BinaryIO | None = None
        try:
            job_file_lock = _acquire_desktop_named_file_lock(f"job-{job_id}")
            with SessionLocal() as session:
                yield session
        finally:
            _release_desktop_file_lock(job_file_lock)
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
