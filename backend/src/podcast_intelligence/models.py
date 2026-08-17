from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from podcast_intelligence.database import Base
from podcast_intelligence.enums import (
    AssetKind,
    EpisodeStatus,
    JobStatus,
    MessageRole,
    ProviderKind,
    SourceType,
    StepStatus,
    SummaryKind,
    TranscriptStatus,
)

JsonType = JSON().with_variant(JSONB, "postgresql")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Workspace(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    shows: Mapped[list[Show]] = relationship(back_populates="workspace")
    episodes: Mapped[list[Episode]] = relationship(back_populates="workspace")


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    external_subject: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Membership(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_membership"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)


class Show(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "shows"
    __table_args__ = (UniqueConstraint("workspace_id", "rss_url", name="uq_show_workspace_rss"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    artwork_url: Mapped[str | None] = mapped_column(Text)
    rss_url: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="shows")
    episodes: Mapped[list[Episode]] = relationship(back_populates="show")


class Episode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "episodes"
    __table_args__ = (
        Index("ix_episode_workspace_status", "workspace_id", "status"),
        Index("ix_episode_workspace_published", "workspace_id", "published_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    show_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shows.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    artwork_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    language: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[EpisodeStatus] = mapped_column(
        Enum(EpisodeStatus, native_enum=False, length=32), default=EpisodeStatus.DRAFT, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    workspace: Mapped[Workspace] = relationship(back_populates="episodes")
    show: Mapped[Show | None] = relationship(back_populates="episodes")
    sources: Mapped[list[EpisodeSource]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    assets: Mapped[list[MediaAsset]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    transcripts: Mapped[list[Transcript]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    speakers: Mapped[list[Speaker]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    summaries: Mapped[list[Summary]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )


class EpisodeSource(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "episode_sources"

    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, native_enum=False, length=32), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(500))
    resolved_media_url: Mapped[str | None] = mapped_column(Text)
    resolution_confidence: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="sources")


class MediaAsset(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (UniqueConstraint("episode_id", "kind", name="uq_episode_asset_kind"),)

    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[AssetKind] = mapped_column(
        Enum(AssetKind, native_enum=False, length=32), nullable=False
    )
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="assets")


class ProcessingJob(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_job_workspace_status", "workspace_id", "status"),
        Index("ix_job_episode_created", "episode_id", "created_at", "updated_at"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32), default=JobStatus.QUEUED, index=True
    )
    current_step: Mapped[str | None] = mapped_column(String(100))
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    options_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    episode: Mapped[Episode] = relationship(back_populates="jobs")
    steps: Mapped[list[ProcessingStep]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="ProcessingStep.ordinal"
    )
    provider_runs: Mapped[list[ProviderRun]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    dispatch: Mapped[JobDispatch | None] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        uselist=False,
    )


class JobDispatch(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "job_dispatches"
    __table_args__ = (
        UniqueConstraint("job_id", name="uq_job_dispatch_job"),
        Index(
            "ix_job_dispatch_pending",
            "dispatched_at",
            "dead_lettered_at",
            "available_at",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    job: Mapped[ProcessingJob] = relationship(back_populates="dispatch")


class ProcessingStep(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "processing_steps"
    __table_args__ = (UniqueConstraint("job_id", "name", name="uq_job_step"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, native_enum=False, length=32), default=StepStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    job: Mapped[ProcessingJob] = relationship(back_populates="steps")


class ProviderRun(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "provider_runs"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ProviderKind] = mapped_column(
        Enum(ProviderKind, native_enum=False, length=32), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200))
    request_id: Mapped[str | None] = mapped_column(String(255))
    input_units: Mapped[float | None] = mapped_column(Float)
    output_units: Mapped[float | None] = mapped_column(Float)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    job: Mapped[ProcessingJob] = relationship(back_populates="provider_runs")


class Transcript(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transcripts"

    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TranscriptStatus] = mapped_column(
        Enum(TranscriptStatus, native_enum=False, length=32), default=TranscriptStatus.PROCESSING
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str | None] = mapped_column(String(32))
    full_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("episode_id", "version", name="uq_transcript_version"),
        Index(
            "ix_transcripts_episode_status_version",
            episode_id,
            status,
            version.desc(),
        ),
    )

    episode: Mapped[Episode] = relationship(back_populates="transcripts")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.ordinal",
    )


class Speaker(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "speakers"
    __table_args__ = (UniqueConstraint("episode_id", "label", name="uq_episode_speaker_label"),)

    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(300))
    confidence: Mapped[float | None] = mapped_column(Float)
    attribution_method: Mapped[str | None] = mapped_column(String(100))
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="speakers")
    segments: Mapped[list[TranscriptSegment]] = relationship(back_populates="speaker")


class TranscriptSegment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("transcript_id", "ordinal", name="uq_transcript_segment_ordinal"),
        Index("ix_segment_transcript_time", "transcript_id", "start_ms"),
    )

    transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), index=True
    )
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("speakers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    language: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    transcript: Mapped[Transcript] = relationship(back_populates="segments")
    speaker: Mapped[Speaker | None] = relationship(back_populates="segments")


class KnowledgeChunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("episode_id", "transcript_id", "ordinal", name="uq_chunk_version_ordinal"),
        Index("ix_chunk_episode_time", "episode_id", "start_ms"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    segment_ids: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    speaker_labels: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="chunks")


class Summary(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "summaries"
    __table_args__ = (
        UniqueConstraint("episode_id", "transcript_id", "kind", "version", name="uq_summary"),
    )

    episode_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[SummaryKind] = mapped_column(
        Enum(SummaryKind, native_enum=False, length=32), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200))
    content_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), default="v1", nullable=False)

    episode: Mapped[Episode] = relationship(back_populates="summaries")


class Conversation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, native_enum=False, length=32), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonType, default=list, nullable=False
    )
    retrieval_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
