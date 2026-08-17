from __future__ import annotations

from enum import StrEnum


class EpisodeStatus(StrEnum):
    DRAFT = "draft"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class SourceType(StrEnum):
    UPLOAD = "upload"
    DIRECT_URL = "direct_url"
    RSS = "rss"
    APPLE = "apple"
    SPOTIFY = "spotify"


class AssetKind(StrEnum):
    ORIGINAL = "original"
    PROCESSING = "processing"
    PLAYBACK = "playback"
    PUBLISHED_TRANSCRIPT = "published_transcript"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TranscriptStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    SUPERSEDED = "superseded"
    FAILED = "failed"


class SummaryKind(StrEnum):
    EXECUTIVE = "executive"
    DETAILED = "detailed"
    CHAPTERS = "chapters"
    TAKEAWAYS = "takeaways"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ProviderKind(StrEnum):
    TRANSCRIPTION = "transcription"
    EMBEDDING = "embedding"
    LLM = "llm"
    RESOLVER = "resolver"
