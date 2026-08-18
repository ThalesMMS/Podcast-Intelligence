from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar

from pydantic import BaseModel

import podcast_intelligence.adapters.ai.openai as openai_adapters
from podcast_intelligence.adapters.ai.openai import (
    OpenAIEmbeddingProvider,
    OpenAILanguageModel,
    OpenAITranscriber,
)
from podcast_intelligence.config import Settings


class _ClientProbe:
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


class _ProbeDocument(BaseModel):
    status: str


def test_provider_specific_openai_keys_override_shared_key(monkeypatch: Any) -> None:
    monkeypatch.setattr(openai_adapters, "OpenAI", _ClientProbe)
    _ClientProbe.calls = []
    settings = Settings(
        _env_file=None,
        openai_api_key="shared",
        openai_base_url="http://gateway.test/v1",
        openai_transcription_api_key="stt",
        openai_embedding_api_key="embedding",
        openai_llm_api_key="llm",
    )

    OpenAITranscriber(settings)
    OpenAIEmbeddingProvider(settings)
    OpenAILanguageModel(settings)

    assert _ClientProbe.calls == [
        {"api_key": "stt", "base_url": "http://gateway.test/v1"},
        {"api_key": "embedding", "base_url": "http://gateway.test/v1"},
        {"api_key": "llm", "base_url": "http://gateway.test/v1"},
    ]


def test_provider_specific_openai_base_urls_override_shared_url(monkeypatch: Any) -> None:
    monkeypatch.setattr(openai_adapters, "OpenAI", _ClientProbe)
    _ClientProbe.calls = []
    settings = Settings(
        _env_file=None,
        openai_api_key="shared",
        openai_base_url="http://fallback.test/v1",
        openai_transcription_base_url="http://transcription.test/v1",
        openai_embedding_base_url="http://embedding.test/v1",
        openai_llm_base_url="http://llm.test/v1",
    )

    OpenAITranscriber(settings)
    OpenAIEmbeddingProvider(settings)
    OpenAILanguageModel(settings)

    assert [call["base_url"] for call in _ClientProbe.calls] == [
        "http://transcription.test/v1",
        "http://embedding.test/v1",
        "http://llm.test/v1",
    ]


def test_provider_clients_fall_back_to_shared_openai_key(monkeypatch: Any) -> None:
    monkeypatch.setattr(openai_adapters, "OpenAI", _ClientProbe)
    _ClientProbe.calls = []
    settings = Settings(
        _env_file=None,
        openai_api_key="shared",
        openai_base_url="http://gateway.test/v1",
    )

    OpenAITranscriber(settings)
    OpenAIEmbeddingProvider(settings)
    OpenAILanguageModel(settings)

    assert [call["api_key"] for call in _ClientProbe.calls] == ["shared", "shared", "shared"]


def test_chat_completions_structured_output_mode() -> None:
    calls: list[dict[str, Any]] = []

    def parse(**kwargs: Any) -> Any:
        calls.append(kwargs)
        message = SimpleNamespace(parsed=_ProbeDocument(status="ok"))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    settings = Settings(
        _env_file=None,
        openai_api_key="shared",
        openai_llm_api="chat_completions",
        openai_reasoning_effort="none",
    )
    model = OpenAILanguageModel.__new__(OpenAILanguageModel)
    model.settings = settings
    model.model_name = "default"
    model.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))

    result = model._parse("system", "user", _ProbeDocument)

    assert result == _ProbeDocument(status="ok")
    assert calls == [
        {
            "model": "default",
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            "response_format": _ProbeDocument,
        }
    ]


def test_embedding_request_can_omit_dimensions_parameter() -> None:
    calls: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.0, 0.1, 0.2, 0.3])])

    settings = Settings(
        _env_file=None,
        openai_api_key="shared",
        openai_embedding_send_dimensions=False,
        embedding_dimension=4,
    )
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.settings = settings
    provider.model_name = "embedding"
    provider.dimension = 4
    provider.client = SimpleNamespace(embeddings=SimpleNamespace(create=create))

    assert provider.embed(["text"]) == [[0.0, 0.1, 0.2, 0.3]]
    assert calls == [{"model": "embedding", "input": ["text"]}]
