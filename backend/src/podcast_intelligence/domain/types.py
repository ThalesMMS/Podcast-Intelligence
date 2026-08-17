from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TranscriptReference(BaseModel):
    url: str
    mime_type: str | None = None
    language: str | None = None
    rel: str | None = None


class ResolvedEpisode(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_type: str
    external_id: str | None = None
    canonical_url: str | None = None
    rss_url: str | None = None
    media_url: str
    media_mime_type: str | None = None
    title: str
    description: str | None = None
    published_at: datetime | None = None
    duration_ms: int | None = None
    language: str | None = None
    artwork_url: str | None = None
    show_title: str | None = None
    show_author: str | None = None
    show_description: str | None = None
    show_artwork_url: str | None = None
    published_transcripts: list[TranscriptReference] = Field(default_factory=list)
    resolution_confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class DownloadedMedia(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: Path
    content_type: str | None = None
    size_bytes: int
    sha256: str
    final_url: str


class AudioMetadata(BaseModel):
    duration_ms: int
    codec_name: str | None = None
    format_name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bit_rate: int | None = None


class TranscriptSegmentData(BaseModel):
    ordinal: int
    start_ms: int
    end_ms: int
    text: str
    speaker_label: str | None = None
    confidence: float | None = None
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptionResult(BaseModel):
    text: str
    segments: list[TranscriptSegmentData]
    language: str | None = None
    provider: str
    model: str | None = None
    request_id: str | None = None
    duration_seconds: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkInput(BaseModel):
    ordinal: int
    text: str
    start_ms: int
    end_ms: int
    segment_ids: list[str]
    speaker_labels: list[str]
    token_count: int


class RetrievedChunk(BaseModel):
    chunk_id: str
    episode_id: str
    episode_title: str
    text: str
    start_ms: int
    end_ms: int
    segment_ids: list[str]
    speaker_labels: list[str]
    lexical_score: float = 0.0
    vector_score: float = 0.0
    combined_score: float = 0.0


class Citation(BaseModel):
    segment_id: str
    start_ms: int
    end_ms: int
    speaker: str | None = None
    quote: str | None = None


class SectionDigest(BaseModel):
    title: str
    summary: str
    start_ms: int
    end_ms: int
    supporting_segment_ids: list[str]
    topics: list[str] = Field(default_factory=list)


class ChapterSummary(BaseModel):
    title: str
    summary: str
    start_ms: int
    end_ms: int
    supporting_segment_ids: list[str]


class KeyPoint(BaseModel):
    text: str
    supporting_segment_ids: list[str]


class EpisodeSummaryDocument(BaseModel):
    executive_summary: str
    detailed_summary: str
    chapters: list[ChapterSummary]
    key_takeaways: list[KeyPoint]
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    open_questions: list[KeyPoint] = Field(default_factory=list)


class AnswerDocument(BaseModel):
    answer: str
    cited_segment_ids: list[str]
    insufficient_evidence: bool = False


class ProviderCapabilities(BaseModel):
    provider: str
    kind: str
    model: str | None = None
    capabilities: dict[str, bool | int | str | list[str]] = Field(default_factory=dict)
