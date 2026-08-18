from __future__ import annotations

from dataclasses import dataclass

from podcast_intelligence.adapters.ai.codex_cli import CodexCLILanguageModel
from podcast_intelligence.adapters.ai.demo import (
    DemoLanguageModel,
    DemoTranscriber,
    DeterministicEmbeddingProvider,
)
from podcast_intelligence.adapters.ai.openai import (
    OpenAIEmbeddingProvider,
    OpenAILanguageModel,
    OpenAITranscriber,
)
from podcast_intelligence.adapters.ai.streaming_stt import StreamingWebSocketTranscriber
from podcast_intelligence.adapters.media.ffmpeg import FFmpegProcessor
from podcast_intelligence.adapters.media.published_transcript import PublishedTranscriptLoader
from podcast_intelligence.adapters.media.safe_http import SafeHTTPClient
from podcast_intelligence.adapters.object_store.local import LocalObjectStore
from podcast_intelligence.adapters.object_store.s3 import S3ObjectStore
from podcast_intelligence.adapters.resolvers.apple import ApplePodcastResolver
from podcast_intelligence.adapters.resolvers.direct import DirectMediaResolver
from podcast_intelligence.adapters.resolvers.rss import RSSResolver
from podcast_intelligence.adapters.resolvers.spotify import SpotifyPodcastResolver
from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import ProviderConfigurationError
from podcast_intelligence.domain.ports import (
    EmbeddingProvider,
    EpisodeResolver,
    LanguageModel,
    ObjectStore,
    Transcriber,
)
from podcast_intelligence.domain.types import ProviderCapabilities
from podcast_intelligence.enums import SourceType


@dataclass(slots=True)
class ProviderRegistry:
    settings: Settings
    http: SafeHTTPClient
    object_store: ObjectStore
    media: FFmpegProcessor
    published_transcripts: PublishedTranscriptLoader
    transcriber: Transcriber
    embeddings: EmbeddingProvider
    llm: LanguageModel
    resolvers: dict[SourceType, EpisodeResolver]

    def resolver_for(self, source_type: SourceType) -> EpisodeResolver:
        try:
            return self.resolvers[source_type]
        except KeyError as exc:
            raise ProviderConfigurationError(
                f"No resolver is registered for source type {source_type}"
            ) from exc

    def capabilities(self) -> list[ProviderCapabilities]:
        resolver_capabilities: list[ProviderCapabilities] = []
        for source_type in self.resolvers:
            resolver_capabilities.append(
                ProviderCapabilities(
                    provider=source_type.value,
                    kind="resolver",
                    model=None,
                    capabilities={
                        "source_type": source_type.value,
                        "authorized_media_only": True,
                    },
                )
            )
        return [
            self.transcriber.capabilities(),
            self.embeddings.capabilities(),
            self.llm.capabilities(),
            *resolver_capabilities,
        ]


def _require_openai_key(
    settings: Settings,
    provider_kind: str,
    key: str | None,
    environment_name: str,
) -> None:
    if not key:
        raise ProviderConfigurationError(
            f"{environment_name} or OPENAI_API_KEY is required when "
            f"{provider_kind} provider is openai"
        )


def build_registry(settings: Settings) -> ProviderRegistry:
    http = SafeHTTPClient(settings)
    object_store: ObjectStore
    if settings.object_store_provider == "local":
        object_store = LocalObjectStore(settings)
    else:
        object_store = S3ObjectStore(settings)
    media = FFmpegProcessor(settings)
    published_transcripts = PublishedTranscriptLoader(http)
    rss = RSSResolver(http)

    if settings.transcription_provider == "openai":
        _require_openai_key(
            settings,
            "transcription",
            settings.openai_key_for("transcription"),
            "OPENAI_TRANSCRIPTION_API_KEY",
        )
        transcriber: Transcriber = OpenAITranscriber(settings)
    elif settings.transcription_provider == "streaming_ws":
        if not settings.streaming_stt_url or not settings.streaming_stt_api_key:
            raise ProviderConfigurationError(
                "STREAMING_STT_URL and STREAMING_STT_API_KEY are required when "
                "transcription provider is streaming_ws"
            )
        transcriber = StreamingWebSocketTranscriber(settings)
    else:
        transcriber = DemoTranscriber()

    if settings.embedding_provider == "openai":
        _require_openai_key(
            settings,
            "embedding",
            settings.openai_key_for("embedding"),
            "OPENAI_EMBEDDING_API_KEY",
        )
        embeddings: EmbeddingProvider = OpenAIEmbeddingProvider(settings)
    else:
        embeddings = DeterministicEmbeddingProvider(settings.embedding_dimension)

    if settings.llm_provider == "openai":
        _require_openai_key(
            settings,
            "LLM",
            settings.openai_key_for("llm"),
            "OPENAI_LLM_API_KEY",
        )
        llm: LanguageModel = OpenAILanguageModel(settings)
    elif settings.llm_provider == "codex_cli":
        llm = CodexCLILanguageModel(settings)
    else:
        llm = DemoLanguageModel()

    resolvers: dict[SourceType, EpisodeResolver] = {
        SourceType.DIRECT_URL: DirectMediaResolver(http),
        SourceType.RSS: rss,
        SourceType.APPLE: ApplePodcastResolver(http, rss),
        SourceType.SPOTIFY: SpotifyPodcastResolver(settings, http, rss),
    }
    return ProviderRegistry(
        settings=settings,
        http=http,
        object_store=object_store,
        media=media,
        published_transcripts=published_transcripts,
        transcriber=transcriber,
        embeddings=embeddings,
        llm=llm,
        resolvers=resolvers,
    )
