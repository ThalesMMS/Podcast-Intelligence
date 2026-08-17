from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import podcast_intelligence.mcp_server as mcp_server
from podcast_intelligence.api.episodes import router
from podcast_intelligence.config import Settings
from podcast_intelligence.database import Base, get_session
from podcast_intelligence.dependencies import (
    AuthContext,
    get_auth_context,
    get_registry,
)
from podcast_intelligence.domain.errors import ConflictError, NotFoundError
from podcast_intelligence.enums import (
    EpisodeStatus,
    JobStatus,
    StepStatus,
    SummaryKind,
    TranscriptStatus,
)
from podcast_intelligence.models import (
    Episode,
    ProcessingJob,
    ProcessingStep,
    Summary,
    Transcript,
    TranscriptSegment,
    Workspace,
)


def _summary_content(label: str) -> dict[str, Any]:
    return {
        "executive_summary": label,
        "detailed_summary": f"{label} details",
        "chapters": [],
        "key_takeaways": [],
        "open_questions": [],
    }


@pytest.fixture
def summary_versions_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, uuid.UUID, uuid.UUID, uuid.UUID]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    workspace = Workspace(name="Summary workspace", slug=f"summary-{uuid.uuid4()}")
    session.add(workspace)
    session.flush()
    current_episode = Episode(
        workspace_id=workspace.id,
        title="Current summary",
        description="Current episode description",
        status=EpisodeStatus.READY,
    )
    stale_episode = Episode(
        workspace_id=workspace.id,
        title="Stale summary",
        description="Fallback episode description",
        status=EpisodeStatus.READY,
    )
    in_flight_episode = Episode(
        workspace_id=workspace.id,
        title="Processing summary",
        description="Processing episode description",
        status=EpisodeStatus.READY,
    )
    session.add_all([current_episode, stale_episode, in_flight_episode])
    session.flush()

    now = datetime.now(UTC)
    old_job = ProcessingJob(
        workspace_id=workspace.id,
        episode_id=current_episode.id,
        status=JobStatus.FAILED,
        current_step="resolve",
        progress=0.25,
        created_at=now - timedelta(days=1),
    )
    current_job = ProcessingJob(
        id=uuid.UUID(int=1),
        workspace_id=workspace.id,
        episode_id=current_episode.id,
        status=JobStatus.RUNNING,
        current_step="transcribe",
        progress=0.75,
        created_at=now,
        updated_at=now,
    )
    tied_older_job = ProcessingJob(
        id=uuid.UUID(int=2),
        workspace_id=workspace.id,
        episode_id=current_episode.id,
        status=JobStatus.FAILED,
        current_step="stale-tie",
        progress=0.25,
        created_at=now,
        updated_at=now - timedelta(seconds=1),
    )
    session.add_all([old_job, current_job, tied_older_job])
    session.flush()
    session.add_all(
        [
            ProcessingStep(
                job_id=old_job.id,
                ordinal=0,
                name="resolve",
                status=StepStatus.FAILED,
            ),
            ProcessingStep(
                job_id=current_job.id,
                ordinal=0,
                name="transcribe",
                status=StepStatus.RUNNING,
            ),
        ]
    )

    current_v1 = Transcript(
        episode_id=current_episode.id,
        version=1,
        status=TranscriptStatus.READY,
        provider="test",
        full_text="old transcript",
    )
    current_v2 = Transcript(
        episode_id=current_episode.id,
        version=2,
        status=TranscriptStatus.READY,
        provider="test",
        full_text="current transcript",
    )
    stale_v1 = Transcript(
        episode_id=stale_episode.id,
        version=1,
        status=TranscriptStatus.READY,
        provider="test",
        full_text="stale transcript",
    )
    stale_v2 = Transcript(
        episode_id=stale_episode.id,
        version=2,
        status=TranscriptStatus.READY,
        provider="test",
        full_text="current transcript without summary",
    )
    processing_transcript = Transcript(
        episode_id=in_flight_episode.id,
        version=1,
        status=TranscriptStatus.PROCESSING,
        provider="test",
        full_text="",
    )
    session.add_all([current_v1, current_v2, stale_v1, stale_v2, processing_transcript])
    session.flush()
    session.add_all(
        [
            TranscriptSegment(
                transcript_id=current_v2.id,
                ordinal=0,
                start_ms=0,
                end_ms=1_000,
                text="current transcript segment",
            ),
            TranscriptSegment(
                transcript_id=stale_v2.id,
                ordinal=0,
                start_ms=0,
                end_ms=1_000,
                text="current transcript without summary",
            ),
            Summary(
                episode_id=current_episode.id,
                transcript_id=current_v1.id,
                kind=SummaryKind.DETAILED,
                version=10,
                provider="test",
                content_json=_summary_content("old-summary"),
            ),
            Summary(
                episode_id=current_episode.id,
                transcript_id=current_v2.id,
                kind=SummaryKind.DETAILED,
                version=1,
                provider="test",
                content_json=_summary_content("current-v1"),
            ),
            Summary(
                episode_id=current_episode.id,
                transcript_id=current_v2.id,
                kind=SummaryKind.DETAILED,
                version=2,
                provider="test",
                content_json=_summary_content("current-v2"),
            ),
            Summary(
                episode_id=stale_episode.id,
                transcript_id=stale_v1.id,
                kind=SummaryKind.DETAILED,
                version=1,
                provider="test",
                content_json=_summary_content("stale-only"),
            ),
        ]
    )
    session.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user_id=uuid.uuid4(),
        workspace_id=workspace.id,
        subject="test",
        claims={},
    )
    app.dependency_overrides[get_registry] = lambda: SimpleNamespace(
        settings=Settings(),
        object_store=None,
    )

    @app.exception_handler(ConflictError)
    def handle_conflict(_: Any, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"message": str(exc)})

    @app.exception_handler(NotFoundError)
    def handle_not_found(_: Any, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"message": str(exc)})

    monkeypatch.setattr(
        mcp_server,
        "SessionLocal",
        sessionmaker(bind=engine, expire_on_commit=False),
    )
    monkeypatch.setattr(mcp_server, "workspace_id", workspace.id)

    with TestClient(app) as client:
        yield client, current_episode.id, stale_episode.id, in_flight_episode.id
    session.close()
    engine.dispose()


def test_episode_reads_only_summaries_for_latest_ready_transcript(
    summary_versions_client: tuple[TestClient, uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    client, episode_id, stale_episode_id, _ = summary_versions_client

    detail = client.get(f"/episodes/{episode_id}")
    summaries = client.get(f"/episodes/{episode_id}/summaries")
    stale_detail = client.get(f"/episodes/{stale_episode_id}")
    stale_summaries = client.get(f"/episodes/{stale_episode_id}/summaries")

    assert detail.status_code == 200
    assert summaries.status_code == 200
    assert [item["version"] for item in detail.json()["summaries"]] == [2, 1]
    assert [item["content_json"]["executive_summary"] for item in summaries.json()] == [
        "current-v2",
        "current-v1",
    ]
    assert stale_detail.status_code == 200
    assert stale_detail.json()["summaries"] == []
    assert stale_summaries.status_code == 200
    assert stale_summaries.json() == []


def test_episode_detail_materializes_only_current_history(
    summary_versions_client: tuple[TestClient, uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    client, episode_id, _, _ = summary_versions_client
    session = client.app.dependency_overrides[get_session]()
    session.expunge_all()
    loaded: list[Any] = []
    statements: list[str] = []

    def capture_load(_: Session, instance: Any) -> None:
        loaded.append(instance)

    def capture_sql(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        statements.append(statement.lower())

    engine = session.get_bind()
    event.listen(session, "loaded_as_persistent", capture_load)
    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        response = client.get(f"/episodes/{episode_id}")
    finally:
        event.remove(session, "loaded_as_persistent", capture_load)
        event.remove(engine, "before_cursor_execute", capture_sql)

    assert response.status_code == 200
    assert response.json()["latest_job"]["current_step"] == "transcribe"
    assert [step["name"] for step in response.json()["latest_job"]["steps"]] == ["transcribe"]
    assert [summary["version"] for summary in response.json()["summaries"]] == [2, 1]
    assert [job.current_step for job in loaded if isinstance(job, ProcessingJob)] == ["transcribe"]
    assert [step.name for step in loaded if isinstance(step, ProcessingStep)] == ["transcribe"]
    assert [summary.version for summary in loaded if isinstance(summary, Summary)] == [2, 1]
    assert not any(isinstance(instance, Transcript) for instance in loaded)

    job_queries = [statement for statement in statements if "from processing_jobs" in statement]
    transcript_queries = [statement for statement in statements if "from transcripts" in statement]
    summary_queries = [statement for statement in statements if "from summaries" in statement]
    assert len(job_queries) == 1
    assert "limit" in job_queries[0]
    assert "processing_jobs.updated_at desc" in job_queries[0]
    assert "processing_jobs.id desc" not in job_queries[0]
    assert len(transcript_queries) == 1
    assert "limit" in transcript_queries[0]
    assert "transcripts.version desc" in transcript_queries[0]
    assert "transcripts.created_at desc" not in transcript_queries[0]
    assert "transcripts.updated_at desc" not in transcript_queries[0]
    assert "transcripts.id desc" not in transcript_queries[0]
    assert len(summary_queries) == 1
    assert "summaries.updated_at desc" in summary_queries[0]
    assert "summaries.kind asc" in summary_queries[0]
    assert "summaries.id desc" not in summary_queries[0]


def test_summary_collection_is_empty_until_a_ready_transcript_exists(
    summary_versions_client: tuple[TestClient, uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    client, _, _, in_flight_episode_id = summary_versions_client

    summaries = client.get(f"/episodes/{in_flight_episode_id}/summaries")
    missing_episode = client.get(f"/episodes/{uuid.uuid4()}/summaries")

    assert summaries.status_code == 200
    assert summaries.json() == []
    assert missing_episode.status_code == 404
    assert missing_episode.json()["message"] == "Episode not found"


def test_exports_do_not_mix_summary_and_transcript_versions(
    summary_versions_client: tuple[TestClient, uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    client, current_episode_id, stale_episode_id, _ = summary_versions_client

    json_export = client.get(f"/episodes/{current_episode_id}/exports/json")
    markdown_export = client.get(f"/episodes/{current_episode_id}/exports/markdown")
    missing_json_summary = client.get(f"/episodes/{stale_episode_id}/exports/json")
    missing_summary = client.get(f"/episodes/{stale_episode_id}/exports/markdown")

    assert json_export.status_code == 200
    assert json_export.json()["summary"]["executive_summary"] == "current-v2"
    assert [item["text"] for item in json_export.json()["transcript"]] == [
        "current transcript segment"
    ]
    assert markdown_export.status_code == 200
    assert "current-v2" in markdown_export.text
    assert "old-summary" not in markdown_export.text
    assert missing_json_summary.status_code == 409
    assert missing_json_summary.json()["message"] == "A summary is required for this export format"
    assert "stale-only" not in missing_json_summary.text
    assert missing_summary.status_code == 409
    assert missing_summary.json()["message"] == "A summary is required for this export format"


def test_mcp_episode_fetch_uses_current_summary_or_description_fallback(
    summary_versions_client: tuple[TestClient, uuid.UUID, uuid.UUID, uuid.UUID],
) -> None:
    _, current_episode_id, stale_episode_id, _ = summary_versions_client

    current = mcp_server.fetch(f"episode:{current_episode_id}")
    stale = mcp_server.fetch(f"episode:{stale_episode_id}")

    assert current["text"] == "current-v2 details"
    assert stale["text"] == "Fallback episode description"
