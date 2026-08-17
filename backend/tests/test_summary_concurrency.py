from __future__ import annotations

import time
import uuid
from collections.abc import Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from podcast_intelligence.database import Base, summary_generation_transaction
from podcast_intelligence.domain.errors import ConflictError
from podcast_intelligence.domain.types import (
    EpisodeSummaryDocument,
    SectionDigest,
)
from podcast_intelligence.enums import TranscriptStatus
from podcast_intelligence.models import Episode, KnowledgeChunk, Transcript, Workspace
from podcast_intelligence.services.summarization import SummaryService


class _CountingLanguageModel:
    provider_name = "test"

    def __init__(self) -> None:
        self.section_calls = 0
        self.synthesis_calls = 0
        self._guard = Lock()

    @property
    def model_name(self) -> str:
        return "test-summary"

    def summarize_section(
        self,
        _episode_title: str,
        section_title: str,
        _transcript: str,
        segment_ids: list[str],
    ) -> SectionDigest:
        with self._guard:
            self.section_calls += 1
        time.sleep(0.05)
        return SectionDigest(
            title=section_title,
            summary="Section summary",
            start_ms=0,
            end_ms=1_000,
            supporting_segment_ids=segment_ids,
        )

    def synthesize_summary(
        self,
        _episode_title: str,
        _section_digests: Sequence[SectionDigest],
    ) -> EpisodeSummaryDocument:
        with self._guard:
            self.synthesis_calls += 1
        return EpisodeSummaryDocument(
            executive_summary="Executive summary",
            detailed_summary="Detailed summary",
            chapters=[],
            key_takeaways=[],
        )


@pytest.fixture
def summary_database(
    tmp_path: Path,
) -> Iterator[tuple[sessionmaker[Session], uuid.UUID, uuid.UUID, uuid.UUID]]:
    database_path = (tmp_path / "summary-concurrency.sqlite").as_posix()
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    with factory() as session:
        workspace = Workspace(name="Concurrent summaries", slug=f"summary-{uuid.uuid4()}")
        session.add(workspace)
        session.flush()
        episode = Episode(workspace_id=workspace.id, title="First episode")
        session.add(episode)
        session.flush()
        transcript = Transcript(
            episode_id=episode.id,
            version=1,
            status=TranscriptStatus.READY,
            provider="test",
            full_text="Transcript",
        )
        session.add(transcript)
        session.flush()
        session.add(
            KnowledgeChunk(
                workspace_id=workspace.id,
                episode_id=episode.id,
                transcript_id=transcript.id,
                ordinal=0,
                start_ms=0,
                end_ms=1_000,
                text="Indexed transcript",
                segment_ids=[str(uuid.uuid4())],
                speaker_labels=[],
                token_count=2,
            )
        )
        session.commit()
        workspace_id = workspace.id
        episode_id = episode.id
        transcript_id = transcript.id

    yield factory, workspace_id, episode_id, transcript_id

    engine.dispose()


def _generate_twice(
    factory: sessionmaker[Session],
    llm: _CountingLanguageModel,
    workspace_id: uuid.UUID,
    episode_id: uuid.UUID,
    *,
    force: bool,
) -> list[tuple[uuid.UUID, int]]:
    start = Barrier(2)

    def generate() -> tuple[uuid.UUID, int]:
        with factory() as session:
            start.wait(timeout=5)
            summary = SummaryService(session, llm).generate(
                workspace_id,
                episode_id,
                force=force,
            )
            return summary.id, summary.version

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(generate) for _ in range(2)]
        return [future.result(timeout=10) for future in futures]


def test_concurrent_default_generation_reuses_one_provider_result(
    summary_database: tuple[sessionmaker[Session], uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    factory, workspace_id, episode_id, _ = summary_database
    llm = _CountingLanguageModel()

    results = _generate_twice(
        factory,
        llm,
        workspace_id,
        episode_id,
        force=False,
    )

    assert len({summary_id for summary_id, _ in results}) == 1
    assert [version for _, version in results] == [1, 1]
    assert llm.section_calls == 1
    assert llm.synthesis_calls == 1


def test_concurrent_forced_generation_creates_monotonic_versions(
    summary_database: tuple[sessionmaker[Session], uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    factory, workspace_id, episode_id, _ = summary_database
    llm = _CountingLanguageModel()

    results = _generate_twice(
        factory,
        llm,
        workspace_id,
        episode_id,
        force=True,
    )

    assert len({summary_id for summary_id, _ in results}) == 2
    assert sorted(version for _, version in results) == [1, 2]
    assert llm.section_calls == 2
    assert llm.synthesis_calls == 2


def test_local_lock_does_not_serialize_different_transcripts(
    summary_database: tuple[sessionmaker[Session], uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    factory, _, _, first_transcript_id = summary_database
    second_transcript_id = uuid.uuid4()
    entered = Barrier(2)

    def acquire(transcript_id: uuid.UUID) -> None:
        with factory() as session, summary_generation_transaction(session, transcript_id):
            entered.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(acquire, first_transcript_id),
            executor.submit(acquire, second_transcript_id),
        ]
        for future in futures:
            future.result(timeout=10)


def test_generation_stops_after_repeated_transcript_changes(
    summary_database: tuple[sessionmaker[Session], uuid.UUID, uuid.UUID, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, workspace_id, episode_id, _ = summary_database
    transcript_lookups = 0

    def changing_transcript(
        _service: SummaryService,
        _episode_id: uuid.UUID,
    ) -> Transcript:
        nonlocal transcript_lookups
        transcript_lookups += 1
        return Transcript(id=uuid.uuid4())

    monkeypatch.setattr(SummaryService, "_latest_transcript", changing_transcript)

    with factory() as session:
        service = SummaryService(session, _CountingLanguageModel())
        with pytest.raises(
            ConflictError,
            match="The episode transcript changed during summary generation",
        ):
            service.generate(workspace_id, episode_id)

    assert transcript_lookups == 10


def test_postgres_summary_lock_is_transaction_scoped() -> None:
    transcript_id = uuid.uuid4()
    statements: list[tuple[str, dict[str, int]]] = []
    commits = 0
    rollbacks = 0

    class _Session:
        def get_bind(self) -> SimpleNamespace:
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement: Any, parameters: dict[str, int]) -> None:
            statements.append((str(statement), parameters))

        def commit(self) -> None:
            nonlocal commits
            commits += 1

        def rollback(self) -> None:
            nonlocal rollbacks
            rollbacks += 1

    with summary_generation_transaction(_Session(), transcript_id):  # type: ignore[arg-type]
        pass

    assert statements[0][0] == "SELECT pg_advisory_xact_lock(:lock_key)"
    assert isinstance(statements[0][1]["lock_key"], int)
    assert commits == 1
    assert rollbacks == 0
