from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from podcast_intelligence.api.episodes import router
from podcast_intelligence.database import Base, get_session
from podcast_intelligence.dependencies import AuthContext, get_auth_context
from podcast_intelligence.enums import EpisodeStatus, TranscriptStatus
from podcast_intelligence.models import (
    Episode,
    Speaker,
    Transcript,
    TranscriptSegment,
    Workspace,
)


@dataclass(frozen=True)
class TranscriptFixture:
    episode_id: uuid.UUID
    segment_ids: list[uuid.UUID]


@pytest.fixture
def transcript_client() -> Iterator[tuple[TestClient, TranscriptFixture]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)

    workspace = Workspace(name="Test workspace", slug=f"test-{uuid.uuid4()}")
    session.add(workspace)
    session.flush()
    episode = Episode(
        workspace_id=workspace.id,
        title="Long episode",
        status=EpisodeStatus.READY,
    )
    session.add(episode)
    session.flush()
    speaker = Speaker(
        episode_id=episode.id,
        label="SPEAKER_00",
        display_name="Alice",
    )
    transcript = Transcript(
        episode_id=episode.id,
        version=1,
        status=TranscriptStatus.READY,
        provider="test",
        language="pt",
        full_text="Large transcript omitted from paginated responses",
    )
    session.add_all([speaker, transcript])
    session.flush()

    segments = [
        TranscriptSegment(
            transcript_id=transcript.id,
            speaker_id=speaker.id,
            ordinal=ordinal,
            start_ms=ordinal * 1_000,
            end_ms=(ordinal + 1) * 1_000,
            text=f"Segment {ordinal}{' needle' if ordinal % 100 == 5 else ''}",
            language="pt",
        )
        for ordinal in range(235)
    ]
    session.add_all(segments)
    session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/v1")

    def override_session() -> Iterator[Session]:
        yield session

    def override_auth() -> AuthContext:
        return AuthContext(
            user_id=uuid.uuid4(),
            workspace_id=workspace.id,
            subject="test-user",
            claims={},
        )

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_auth_context] = override_auth

    with TestClient(app) as client:
        yield (
            client,
            TranscriptFixture(
                episode_id=episode.id,
                segment_ids=[segment.id for segment in segments],
            ),
        )

    session.close()
    Base.metadata.drop_all(engine)


def test_transcript_cursor_pagination_is_bounded_and_stable(
    transcript_client: tuple[TestClient, TranscriptFixture],
) -> None:
    client, fixture = transcript_client

    first = client.get(f"/v1/episodes/{fixture.episode_id}/transcript", params={"limit": 50})
    assert first.status_code == 200
    first_page = first.json()
    assert [segment["ordinal"] for segment in first_page["segments"]] == list(range(50))
    assert first_page["segment_count"] == 235
    assert first_page["matched_count"] == 235
    assert first_page["limit"] == 50
    assert first_page["next_cursor"]
    assert "full_text" not in first_page
    assert len(first.content) < 256 * 1024

    second = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"limit": 50, "cursor": first_page["next_cursor"]},
    )
    assert second.status_code == 200
    assert [segment["ordinal"] for segment in second.json()["segments"]] == list(range(50, 100))


def test_transcript_search_uses_its_own_cursor_scope(
    transcript_client: tuple[TestClient, TranscriptFixture],
) -> None:
    client, fixture = transcript_client

    first = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"limit": 2, "q": "  NEEDLE  "},
    )
    assert first.status_code == 200
    page = first.json()
    assert page["query"] == "needle"
    assert page["matched_count"] == 3
    assert [segment["ordinal"] for segment in page["segments"]] == [5, 105]

    second = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"limit": 2, "q": "needle", "cursor": page["next_cursor"]},
    )
    assert [segment["ordinal"] for segment in second.json()["segments"]] == [205]
    assert second.json()["next_cursor"] is None

    mismatched = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"limit": 2, "q": "different", "cursor": page["next_cursor"]},
    )
    assert mismatched.status_code == 400
    assert mismatched.json()["detail"] == "Invalid transcript cursor"


def test_transcript_timestamp_page_contains_and_identifies_anchor(
    transcript_client: tuple[TestClient, TranscriptFixture],
) -> None:
    client, fixture = transcript_client

    response = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"limit": 10, "at_ms": 125_500},
    )

    assert response.status_code == 200
    page = response.json()
    assert [segment["ordinal"] for segment in page["segments"]] == list(range(120, 130))
    assert page["anchor_segment_id"] == str(fixture.segment_ids[125])


def test_transcript_timestamp_page_with_limit_one_preserves_anchor(
    transcript_client: tuple[TestClient, TranscriptFixture],
) -> None:
    client, fixture = transcript_client

    response = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"limit": 1, "at_ms": 125_500},
    )

    assert response.status_code == 200
    page = response.json()
    assert [segment["ordinal"] for segment in page["segments"]] == [125]
    assert page["anchor_segment_id"] == str(fixture.segment_ids[125])


@pytest.mark.parametrize("transcript_id", [None, 123, [], {}])
def test_transcript_rejects_non_string_cursor_transcript_id(
    transcript_client: tuple[TestClient, TranscriptFixture],
    transcript_id: object,
) -> None:
    client, fixture = transcript_client
    payload = json.dumps(
        {"transcript_id": transcript_id, "ordinal": 0, "query": None},
        separators=(",", ":"),
    ).encode()
    cursor = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()

    response = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"cursor": cursor},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid transcript cursor"


def test_transcript_rejects_invalid_or_ambiguous_cursors(
    transcript_client: tuple[TestClient, TranscriptFixture],
) -> None:
    client, fixture = transcript_client

    invalid = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"cursor": "not-a-cursor"},
    )
    assert invalid.status_code == 400

    ambiguous = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"cursor": "not-a-cursor", "at_ms": 10_000},
    )
    assert ambiguous.status_code == 400
    assert ambiguous.json()["detail"] == "cursor and at_ms cannot be combined"

    oversized = client.get(
        f"/v1/episodes/{fixture.episode_id}/transcript",
        params={"limit": 201},
    )
    assert oversized.status_code == 422
