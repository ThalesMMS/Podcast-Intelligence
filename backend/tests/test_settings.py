from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from podcast_intelligence.config import Settings


def test_embedding_batch_size_defaults_to_four(monkeypatch: Any) -> None:
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)
    settings = Settings(_env_file=None)
    assert settings.embedding_batch_size == 4


def test_openai_reasoning_effort_defaults_to_none(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_reasoning_effort == "none"


def test_structured_output_defaults_to_chat_completions(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_LLM_API", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_llm_api == "chat_completions"


def test_embedding_dimensions_parameter_is_disabled_by_default(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_EMBEDDING_SEND_DIMENSIONS", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_embedding_send_dimensions is False


def test_websocket_url_in_openai_transcription_settings_migrates_to_streaming() -> None:
    settings = Settings(
        _env_file=None,
        ai_profile="openai",
        transcription_provider="openai",
        embedding_provider="openai",
        llm_provider="openai",
        openai_transcription_base_url=("ws://transcription.test/v1/audio/transcriptions/stream"),
        openai_transcription_api_key="transcription-key",
        openai_transcription_model="whisper-large-v3-turbo",
    )

    assert settings.ai_profile == "custom"
    assert settings.transcription_provider == "streaming_ws"
    assert settings.embedding_provider == "openai"
    assert settings.llm_provider == "openai"
    assert settings.streaming_stt_url == "ws://transcription.test/v1/audio/transcriptions/stream"
    assert settings.streaming_stt_api_key == "transcription-key"
    assert settings.streaming_stt_model == "whisper-large-v3-turbo"
    assert settings.openai_transcription_base_url is None
    assert settings.openai_transcription_api_key is None


def test_openai_embedding_base_url_rejects_websocket_protocol() -> None:
    with pytest.raises(ValidationError, match="HTTP-compatible base URLs"):
        Settings(
            _env_file=None,
            ai_profile="custom",
            embedding_provider="openai",
            openai_embedding_base_url="ws://embedding.test/v1",
        )


def test_streaming_transcription_url_rejects_http_protocol() -> None:
    with pytest.raises(ValidationError, match="WebSocket transcription URL"):
        Settings(
            _env_file=None,
            ai_profile="custom",
            transcription_provider="streaming_ws",
            streaming_stt_url="http://transcription.test/v1",
            streaming_stt_api_key="transcription-key",
        )


def test_desktop_profile_selects_local_infrastructure(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        desktop_mode=True,
        desktop_data_dir=tmp_path,
    )
    assert settings.object_store_provider == "local"
    assert settings.job_backend == "local"
    assert settings.auth_mode == "dev"
    assert settings.local_storage_dir == tmp_path / "objects"
    assert settings.processing_temp_dir == tmp_path / "tmp"
    assert settings.database_url.startswith("sqlite+pysqlite:///")
