from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from podcast_intelligence.api.episodes import router
from podcast_intelligence.database import Base, get_session
from podcast_intelligence.dependencies import AuthContext, get_auth_context
from podcast_intelligence.enums import EpisodeStatus
from podcast_intelligence.models import Episode, Workspace


@pytest.fixture
def episode_list_client() -> Iterator[TestClient]:
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
    created_at = datetime(2026, 1, 1, tzinfo=UTC)
    session.add_all(
        [
            Episode(
                id=uuid.UUID(int=index),
                workspace_id=workspace.id,
                title=f"Episode {index}",
                status=EpisodeStatus.PROCESSING if index == 1 else EpisodeStatus.READY,
                created_at=created_at,
            )
            for index in range(1, 5)
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

    with TestClient(app) as client:
        yield client
    session.close()


def test_episode_list_has_stable_order_and_global_active_count(
    episode_list_client: TestClient,
) -> None:
    first_page = episode_list_client.get("/episodes", params={"limit": 2, "offset": 0})
    second_page = episode_list_client.get("/episodes", params={"limit": 2, "offset": 2})

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert [item["title"] for item in first_page.json()["items"]] == ["Episode 4", "Episode 3"]
    assert [item["title"] for item in second_page.json()["items"]] == ["Episode 2", "Episode 1"]
    assert first_page.json()["total"] == 4
    assert first_page.json()["active_count"] == 1
