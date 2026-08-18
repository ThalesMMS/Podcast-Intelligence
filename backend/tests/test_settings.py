from __future__ import annotations

from typing import Any

from podcast_intelligence.config import Settings


def test_embedding_batch_size_defaults_to_four(monkeypatch: Any) -> None:
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)
    settings = Settings(_env_file=None)
    assert settings.embedding_batch_size == 4


def test_openai_reasoning_effort_defaults_to_none(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)
    settings = Settings(_env_file=None)
    assert settings.openai_reasoning_effort == "none"
