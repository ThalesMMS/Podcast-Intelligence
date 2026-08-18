from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _uses_url_protocol(value: str | None, protocols: tuple[str, ...]) -> bool:
    normalized = (value or "").strip().lower()
    return normalized.startswith(tuple(f"{protocol}://" for protocol in protocols))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = True
    app_secret_key: str = "change-me-in-production"
    app_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    default_workspace_id: str = "00000000-0000-0000-0000-000000000001"

    # Desktop mode replaces PostgreSQL, Redis/Celery and S3/MinIO with local
    # equivalents while retaining the same domain services and HTTP contracts.
    desktop_mode: bool = False
    desktop_api_token: str | None = None
    desktop_api_base_url: str = "http://127.0.0.1:8000"
    desktop_data_dir: Path = Path(".podcast-intelligence")
    desktop_job_workers: int = Field(default=2, ge=1, le=8)
    desktop_job_poll_seconds: float = Field(default=0.4, gt=0.05, le=10)
    desktop_mcp_enabled: bool = True

    database_url: str = "postgresql+psycopg://podcast:podcast@localhost:5432/podcast_intelligence"
    redis_url: str = "redis://localhost:6379/0"
    job_backend: Literal["celery", "local"] = "celery"

    object_store_provider: Literal["s3", "local"] = "s3"
    local_storage_dir: Path = Path(".podcast-intelligence/storage")
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "podcast"
    s3_secret_key: str = "podcast-secret"
    s3_bucket: str = "podcast-media"
    s3_region: str = "us-east-1"
    s3_secure: bool = False
    playback_url_expires_seconds: int = Field(default=900, ge=60, le=604800)

    auth_mode: Literal["dev", "oidc"] = "dev"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_workspace_claim: str = "workspace_id"

    ai_profile: Literal["demo", "openai", "custom"] = "demo"
    transcription_provider: Literal["demo", "openai", "streaming_ws"] = "demo"
    embedding_provider: Literal["demo", "openai"] = "demo"
    llm_provider: Literal["demo", "openai", "codex_cli"] = "demo"

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_transcription_base_url: str | None = None
    openai_embedding_base_url: str | None = None
    openai_llm_base_url: str | None = None
    openai_transcription_api_key: str | None = None
    openai_embedding_api_key: str | None = None
    openai_llm_api_key: str | None = None
    openai_transcription_model: str = "gpt-4o-transcribe-diarize"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_llm_model: str = "gpt-5.6-luna"
    openai_llm_api: Literal["responses", "chat_completions"] = "chat_completions"
    openai_embedding_send_dimensions: bool = False
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "none"
    openai_max_upload_bytes: int = 24 * 1024 * 1024
    transcription_chunk_seconds: int = 15 * 60
    transcription_chunk_bitrate: str = "64k"
    embedding_dimension: int = Field(default=1536, ge=1, le=16_000)
    embedding_batch_size: int = Field(default=4, ge=1, le=2048)

    streaming_stt_url: str | None = None
    streaming_stt_api_key: str | None = None
    streaming_stt_model: str = "default"
    streaming_stt_language: str = "pt"
    streaming_stt_frame_seconds: float = Field(default=10.0, gt=0, le=30)
    streaming_stt_batch_seconds: float = Field(default=120.0, gt=0, le=600)
    streaming_stt_open_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    streaming_stt_close_timeout_seconds: float = Field(default=10.0, gt=0, le=120)

    codex_binary: str = "codex"
    codex_model: str | None = None
    codex_timeout_seconds: int = 300
    codex_workdir: Path = Path("/tmp/podcast-intelligence-codex")

    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    http_user_agent: str = "PodcastIntelligence/0.2 (+https://localhost)"
    max_remote_file_bytes: int = 1024 * 1024 * 1024
    max_audio_duration_seconds: int = 6 * 60 * 60
    download_timeout_seconds: int = 120
    dispatch_max_attempts: int = Field(default=10, ge=1, le=1000)
    dispatch_run_time_budget_seconds: float = Field(default=30.0, gt=0, le=300)

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    processing_temp_dir: Path = Path("/tmp/podcast-intelligence")

    chunk_target_tokens: int = 600
    chunk_overlap_tokens: int = 80
    retrieval_top_k: int = 10
    retrieval_lexical_weight: float = 0.35
    retrieval_vector_weight: float = 0.65

    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001

    @field_validator("app_allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def openai_key_for(
        self, provider_kind: Literal["transcription", "embedding", "llm"]
    ) -> str | None:
        provider_keys = {
            "transcription": self.openai_transcription_api_key,
            "embedding": self.openai_embedding_api_key,
            "llm": self.openai_llm_api_key,
        }
        return provider_keys[provider_kind] or self.openai_api_key

    def openai_base_url_for(
        self, provider_kind: Literal["transcription", "embedding", "llm"]
    ) -> str | None:
        provider_urls = {
            "transcription": self.openai_transcription_base_url,
            "embedding": self.openai_embedding_base_url,
            "llm": self.openai_llm_base_url,
        }
        return provider_urls[provider_kind] or self.openai_base_url

    @model_validator(mode="after")
    def apply_profile_and_validate(self) -> Settings:
        openai_profile = self.ai_profile == "openai"
        transcription_url = (self.openai_transcription_base_url or "").strip()
        if _uses_url_protocol(transcription_url, ("ws", "wss")):
            self.ai_profile = "custom"
            self.transcription_provider = "streaming_ws"
            if openai_profile:
                self.embedding_provider = "openai"
                self.llm_provider = "openai"
            self.streaming_stt_url = self.streaming_stt_url or transcription_url
            self.streaming_stt_api_key = (
                self.streaming_stt_api_key
                or self.openai_transcription_api_key
                or self.openai_api_key
            )
            if not self.streaming_stt_model or self.streaming_stt_model == "default":
                self.streaming_stt_model = self.openai_transcription_model
            self.openai_transcription_base_url = None
            self.openai_transcription_api_key = None
        elif openai_profile:
            self.transcription_provider = "openai"
            self.embedding_provider = "openai"
            self.llm_provider = "openai"

        http_base_urls = {
            "OPENAI_BASE_URL": self.openai_base_url,
            "OPENAI_TRANSCRIPTION_BASE_URL": self.openai_transcription_base_url,
            "OPENAI_EMBEDDING_BASE_URL": self.openai_embedding_base_url,
            "OPENAI_LLM_BASE_URL": self.openai_llm_base_url,
        }
        invalid_http_urls = [
            name
            for name, value in http_base_urls.items()
            if value and not _uses_url_protocol(value, ("http", "https"))
        ]
        if invalid_http_urls:
            raise ValueError(
                "HTTP-compatible base URLs must use http:// or https://: "
                + ", ".join(invalid_http_urls)
            )
        if self.streaming_stt_url and not _uses_url_protocol(self.streaming_stt_url, ("ws", "wss")):
            raise ValueError("WebSocket transcription URL must use ws:// or wss://")

        if self.desktop_mode:
            self.object_store_provider = "local"
            self.job_backend = "local"
            self.auth_mode = "dev"
            self.app_env = "production"
            self.app_debug = False
            self.desktop_data_dir = self.desktop_data_dir.expanduser().resolve()

            # Keep every mutable artifact below the operating system's private
            # application-data directory unless the launcher supplied an
            # explicit location.
            if self.database_url.startswith("postgresql"):
                database_path = self.desktop_data_dir / "podcast-intelligence.sqlite3"
                self.database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
            if self.local_storage_dir == Path(".podcast-intelligence/storage"):
                self.local_storage_dir = self.desktop_data_dir / "objects"
            else:
                self.local_storage_dir = self.local_storage_dir.expanduser().resolve()
            if self.processing_temp_dir == Path("/tmp/podcast-intelligence"):
                self.processing_temp_dir = self.desktop_data_dir / "tmp"
            else:
                self.processing_temp_dir = self.processing_temp_dir.expanduser().resolve()
            if self.codex_workdir == Path("/tmp/podcast-intelligence-codex"):
                self.codex_workdir = self.desktop_data_dir / "codex"
            else:
                self.codex_workdir = self.codex_workdir.expanduser().resolve()

        if self.app_env == "production" and self.auth_mode == "dev" and not self.desktop_mode:
            raise ValueError("AUTH_MODE=dev is forbidden in production outside desktop mode")

        if self.auth_mode == "oidc" and not (
            self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url
        ):
            raise ValueError("OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL are required")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
