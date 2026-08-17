from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from podcast_intelligence.domain.types import (
    AnswerDocument,
    EpisodeSummaryDocument,
    ProviderCapabilities,
    ResolvedEpisode,
    RetrievedChunk,
    SectionDigest,
    TranscriptionResult,
)


class ObjectStore(Protocol):
    def presign_post(
        self,
        object_key: str,
        content_type: str,
        expected_size_bytes: int,
        expires_seconds: int = 900,
    ) -> dict[str, Any]: ...

    def presign_get(self, object_key: str, expires_seconds: int = 900) -> str: ...

    def upload_file(
        self, source: Path, object_key: str, content_type: str | None = None
    ) -> None: ...

    def download_file(self, object_key: str, destination: Path) -> None: ...

    def head(self, object_key: str) -> dict[str, Any]: ...

    def delete(self, object_key: str) -> None: ...


class EpisodeResolver(Protocol):
    source_type: str

    def resolve(
        self,
        url: str,
        *,
        episode_guid: str | None = None,
        episode_title: str | None = None,
        rss_url_hint: str | None = None,
    ) -> ResolvedEpisode: ...


class Transcriber(Protocol):
    provider_name: str

    @property
    def model_name(self) -> str | None: ...

    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
        known_speakers: dict[str, Path] | None = None,
    ) -> TranscriptionResult: ...

    def capabilities(self) -> ProviderCapabilities: ...


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def capabilities(self) -> ProviderCapabilities: ...


class LanguageModel(Protocol):
    provider_name: str

    @property
    def model_name(self) -> str | None: ...

    def summarize_section(
        self, episode_title: str, section_title: str, transcript: str, segment_ids: list[str]
    ) -> SectionDigest: ...

    def synthesize_summary(
        self, episode_title: str, section_digests: Sequence[SectionDigest]
    ) -> EpisodeSummaryDocument: ...

    def answer(
        self,
        question: str,
        contexts: Sequence[RetrievedChunk],
        conversation_history: Sequence[dict[str, str]],
    ) -> AnswerDocument: ...

    def capabilities(self) -> ProviderCapabilities: ...
