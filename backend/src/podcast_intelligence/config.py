from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    database_url: str = "postgresql+psycopg://podcast:podcast@localhost:5432/podcast_intelligence"
    redis_url: str = "redis://localhost:6379/0"

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
    openai_transcription_api_key: str | None = None
    openai_embedding_api_key: str | None = None
    openai_llm_api_key: str | None = None
    openai_transcription_model: str = "gpt-4o-transcribe-diarize"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_llm_model: str = "gpt-5.6-luna"
    openai_llm_api: Literal["responses", "chat_completions"] = "responses"
    openai_embedding_send_dimensions: bool = True
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    openai_max_upload_bytes: int = 24 * 1024 * 1024
    transcription_chunk_seconds: int = 15 * 60
    transcription_chunk_bitrate: str = "64k"
    embedding_dimension: int = Field(default=1536, ge=1, le=16_000)
    embedding_batch_size: int = Field(default=8, ge=1, le=2048)

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
    http_user_agent: str = "PodcastIntelligence/0.1 (+https://localhost)"
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

    mcp_host: str = "0.0.0.0"
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

    @model_validator(mode="after")
    def apply_profile_and_validate(self) -> Settings:
        if self.ai_profile == "openai":
            self.transcription_provider = "openai"
            self.embedding_provider = "openai"
            self.llm_provider = "openai"

        if self.app_env == "production" and self.auth_mode == "dev":
            raise ValueError("AUTH_MODE=dev is forbidden in production")

        if self.auth_mode == "oidc" and not (
            self.oidc_issuer and self.oidc_audience and self.oidc_jwks_url
        ):
            raise ValueError("OIDC_ISSUER, OIDC_AUDIENCE and OIDC_JWKS_URL are required")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
