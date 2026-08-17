from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from podcast_intelligence.schemas import (
    ConversationCreateRequest,
    ImportOptions,
    ImportRequest,
    ImportSourceInput,
    SpeakerUpdate,
)


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("filename", 1000),
        ("content_type", 255),
        ("episode_guid", 500),
        ("episode_title", 1000),
    ],
)
def test_import_source_string_limits(field: str, limit: int) -> None:
    payload = {"type": "upload", "object_key": "workspace/uploads/file", field: "x" * limit}

    assert getattr(ImportSourceInput.model_validate(payload), field) == "x" * limit
    with pytest.raises(ValidationError):
        ImportSourceInput.model_validate({**payload, field: "x" * (limit + 1)})


def test_import_title_override_matches_episode_column_limit() -> None:
    assert ImportOptions(title_override="x" * 1000).title_override == "x" * 1000
    with pytest.raises(ValidationError):
        ImportOptions(title_override="x" * 1001)


def test_language_is_normalized_and_limited() -> None:
    assert ImportOptions(language="PT_br").language == "pt-BR"
    exact_limit = "aa-aaaaaaaa-aaaaaaaa-aaaaaaaa-bb"
    over_limit = "aa-aaaaaaaa-aaaaaaaa-aaaaaaaa-bbb"

    assert len(exact_limit) == 32
    assert ImportOptions(language=exact_limit).language == "aa-aaaaaaaa-aaaaaaaa-aaaaaaaa-BB"
    with pytest.raises(ValidationError):
        ImportOptions(language=over_limit)
    with pytest.raises(ValidationError):
        ImportOptions(language="pt--BR")


def test_conversation_and_speaker_limits_match_database_columns() -> None:
    episode_id = uuid.uuid4()
    assert len(ConversationCreateRequest(episode_id=episode_id, title="x" * 500).title or "") == 500
    assert len(SpeakerUpdate(display_name="x" * 300).display_name) == 300

    with pytest.raises(ValidationError):
        ConversationCreateRequest(episode_id=episode_id, title="x" * 501)
    with pytest.raises(ValidationError):
        SpeakerUpdate(display_name="x" * 301)


def test_invalid_import_returns_422_before_handler_runs() -> None:
    app = FastAPI()
    handler_calls = 0

    @app.post("/imports")
    def create_import(_request: ImportRequest) -> dict[str, bool]:
        nonlocal handler_calls
        handler_calls += 1
        return {"created": True}

    response = TestClient(app).post(
        "/imports",
        json={
            "source": {
                "type": "upload",
                "object_key": "workspace/uploads/file",
                "episode_title": "x" * 1001,
            }
        },
    )

    assert response.status_code == 422
    assert handler_calls == 0
