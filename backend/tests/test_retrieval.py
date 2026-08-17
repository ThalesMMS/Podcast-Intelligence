from __future__ import annotations

import uuid
from collections import namedtuple
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from podcast_intelligence.config import Settings
from podcast_intelligence.database import Base
from podcast_intelligence.enums import TranscriptStatus
from podcast_intelligence.models import Episode, KnowledgeChunk, Transcript, Workspace
from podcast_intelligence.services.retrieval import RetrievalService, _vector_similarity


@pytest.mark.parametrize(
    ("distance", "expected"),
    [
        (0.0, 1.0),
        (1.0, 0.0),
        (None, 0.0),
        (0.25, 0.75),
        (1.25, 0.0),
    ],
)
def test_vector_similarity(distance: float | None, expected: float) -> None:
    assert _vector_similarity(distance) == expected


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class _Session:
    def __init__(self, vector_rows: list[Any], lexical_rows: list[Any]) -> None:
        self.results = iter((_Rows(vector_rows), _Rows(lexical_rows)))
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> _Rows:
        self.statements.append(statement)
        return next(self.results)


class _Embeddings:
    model_name = "test-embedding"

    def embed(self, texts: list[str]) -> list[list[float]]:
        assert texts == ["exact match"]
        return [[0.0] * 1536]


def _chunk(workspace_id: uuid.UUID, episode_id: uuid.UUID, text: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        episode_id=episode_id,
        transcript_id=uuid.uuid4(),
        ordinal=0,
        start_ms=0,
        end_ms=1_000,
        text=text,
        segment_ids=[],
        speaker_labels=[],
        token_count=2,
        embedding=[0.0] * 1536,
        metadata_json={},
    )


def test_exact_vector_match_remains_first_in_hybrid_ranking() -> None:
    workspace_id = uuid.uuid4()
    episode_id = uuid.uuid4()
    episode = Episode(id=episode_id, workspace_id=workspace_id, title="Episode")
    exact = _chunk(workspace_id, episode_id, "exact")
    lexical = _chunk(workspace_id, episode_id, "lexical")
    lexical_row = namedtuple("LexicalRow", ["chunk", "episode", "rank"])

    session = _Session(
        vector_rows=[(exact, episode, 0.0), (lexical, episode, 0.8)],
        lexical_rows=[lexical_row(lexical, episode, 1.0)],
    )
    service = RetrievalService(session, Settings(), _Embeddings())  # type: ignore[arg-type]

    results = service.search(workspace_id, "exact match")

    assert [result.chunk_id for result in results] == [str(exact.id), str(lexical.id)]
    assert results[0].vector_score == 1.0
    assert results[0].combined_score > results[1].combined_score


def test_lexical_query_uses_gin_compatible_match_predicate_and_scope() -> None:
    workspace_id = uuid.uuid4()
    episode_id = uuid.uuid4()
    session = _Session(vector_rows=[], lexical_rows=[])
    service = RetrievalService(session, Settings(), _Embeddings())  # type: ignore[arg-type]

    service.search(workspace_id, "exact match", episode_id=episode_id)

    vector_sql = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    lexical_sql = str(
        session.statements[1].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "knowledge_chunks.embedding_model = 'test-embedding'" in vector_sql
    assert "to_tsvector('simple'::regconfig, knowledge_chunks.text)" in lexical_sql
    assert "websearch_to_tsquery('simple'::regconfig, 'exact match')" in lexical_sql
    assert " @@ " in lexical_sql
    assert f"knowledge_chunks.workspace_id = '{workspace_id}'" in lexical_sql
    assert f"knowledge_chunks.episode_id = '{episode_id}'" in lexical_sql
    assert "knowledge_chunks.transcript_id = (SELECT transcripts.id" in lexical_sql
    assert "transcripts.episode_id = knowledge_chunks.episode_id" in lexical_sql
    assert "transcripts.status = 'READY'" in lexical_sql


def test_base_query_only_uses_chunks_from_latest_ready_transcript() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        workspace = Workspace(name="Retrieval workspace", slug=f"retrieval-{uuid.uuid4()}")
        session.add(workspace)
        session.flush()
        episodes = [
            Episode(workspace_id=workspace.id, title="First episode"),
            Episode(workspace_id=workspace.id, title="Second episode"),
        ]
        session.add_all(episodes)
        session.flush()

        first_v1 = Transcript(
            episode_id=episodes[0].id,
            version=1,
            status=TranscriptStatus.READY,
            provider="test",
            full_text="old",
        )
        first_v2 = Transcript(
            episode_id=episodes[0].id,
            version=2,
            status=TranscriptStatus.READY,
            provider="test",
            full_text="current",
        )
        first_processing = Transcript(
            episode_id=episodes[0].id,
            version=3,
            status=TranscriptStatus.PROCESSING,
            provider="test",
            full_text="not ready",
        )
        second_v1 = Transcript(
            episode_id=episodes[1].id,
            version=1,
            status=TranscriptStatus.READY,
            provider="test",
            full_text="second",
        )
        transcripts = [first_v1, first_v2, first_processing, second_v1]
        session.add_all(transcripts)
        session.flush()

        chunks = [
            _chunk(workspace.id, episodes[0].id, "old"),
            _chunk(workspace.id, episodes[0].id, "current"),
            _chunk(workspace.id, episodes[0].id, "not ready"),
            _chunk(workspace.id, episodes[1].id, "second"),
        ]
        for chunk, transcript in zip(chunks, transcripts, strict=True):
            chunk.transcript_id = transcript.id
            chunk.embedding = None
        session.add_all(chunks)
        session.commit()

        service = RetrievalService(session, Settings(), _Embeddings())
        workspace_rows = session.execute(service._base_query(workspace.id, None)).all()
        episode_rows = session.execute(service._base_query(workspace.id, episodes[0].id)).all()

    engine.dispose()
    assert {chunk.text for chunk, _ in workspace_rows} == {"current", "second"}
    assert [chunk.text for chunk, _ in episode_rows] == ["current"]
