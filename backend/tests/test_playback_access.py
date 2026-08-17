from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from podcast_intelligence.api.episodes import router
from podcast_intelligence.config import Settings
from podcast_intelligence.database import Base, get_session
from podcast_intelligence.dependencies import AuthContext, get_auth_context, get_registry
from podcast_intelligence.domain.errors import NotFoundError
from podcast_intelligence.enums import AssetKind, EpisodeStatus
from podcast_intelligence.models import Episode, MediaAsset, Workspace


class _ObjectStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def presign_get(self, object_key: str, expires_seconds: int = 900) -> str:
        self.calls.append((object_key, expires_seconds))
        return f"https://media.example/{object_key}?expires={expires_seconds}"


@pytest.fixture
def playback_client() -> Iterator[tuple[TestClient, uuid.UUID, uuid.UUID, _ObjectStore]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    workspace = Workspace(name="Playback workspace", slug=f"playback-{uuid.uuid4()}")
    other_workspace = Workspace(name="Other workspace", slug=f"other-{uuid.uuid4()}")
    session.add_all([workspace, other_workspace])
    session.flush()
    episode = Episode(
        workspace_id=workspace.id,
        title="Private playback",
        status=EpisodeStatus.READY,
    )
    foreign_episode = Episode(
        workspace_id=other_workspace.id,
        title="Foreign playback",
        status=EpisodeStatus.READY,
    )
    session.add_all([episode, foreign_episode])
    session.flush()
    session.add_all(
        [
            MediaAsset(
                episode_id=episode.id,
                kind=AssetKind.PLAYBACK,
                object_key=f"{workspace.id}/episodes/{episode.id}/playback/audio.m4a",
            ),
            MediaAsset(
                episode_id=foreign_episode.id,
                kind=AssetKind.PLAYBACK,
                object_key=(
                    f"{other_workspace.id}/episodes/{foreign_episode.id}/playback/audio.m4a"
                ),
            ),
        ]
    )
    session.commit()

    store = _ObjectStore()
    registry = SimpleNamespace(
        settings=Settings(playback_url_expires_seconds=120),
        object_store=store,
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        user_id=uuid.uuid4(),
        workspace_id=workspace.id,
        subject="test",
        claims={},
    )
    app.dependency_overrides[get_registry] = lambda: registry

    @app.exception_handler(NotFoundError)
    def handle_not_found(_: Any, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"message": str(exc)})

    with TestClient(app) as client:
        yield client, episode.id, foreign_episode.id, store
    session.close()
    engine.dispose()


def test_playback_access_is_scoped_and_reports_expiration(
    playback_client: tuple[TestClient, uuid.UUID, uuid.UUID, _ObjectStore],
) -> None:
    client, episode_id, _, store = playback_client
    before = datetime.now().astimezone()

    response = client.get(f"/episodes/{episode_id}/playback")

    assert response.status_code == 200
    body = response.json()
    assert body["playback_url"].startswith("https://media.example/")
    assert body["expires_in"] == 120
    assert datetime.fromisoformat(body["expires_at"]) > before
    assert len(store.calls) == 1
    assert store.calls[0][0].endswith(f"/episodes/{episode_id}/playback/audio.m4a")
    assert store.calls[0][1] == 120


def test_playback_access_does_not_sign_another_workspaces_asset(
    playback_client: tuple[TestClient, uuid.UUID, uuid.UUID, _ObjectStore],
) -> None:
    client, _, foreign_episode_id, store = playback_client

    response = client.get(f"/episodes/{foreign_episode_id}/playback")

    assert response.status_code == 404
    assert response.json()["message"] == "Playback not found"
    assert store.calls == []
