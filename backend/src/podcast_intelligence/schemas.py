from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from podcast_intelligence.domain.types import EpisodeSummaryDocument, ProviderCapabilities
from podcast_intelligence.enums import EpisodeStatus, JobStatus, SourceType, StepStatus

_UPLOAD_CONTENT_TYPE_RE = re.compile(r"^(?:audio|video)/[a-z0-9][a-z0-9!#$&^_.+-]*$")


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict[str, str] = Field(default_factory=dict)


class UploadInitiateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)

    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _UPLOAD_CONTENT_TYPE_RE.fullmatch(normalized):
            raise ValueError("content_type must be a concrete audio or video MIME type")
        return normalized


class UploadInitiateResponse(BaseModel):
    object_key: str
    upload_url: str
    method: Literal["POST"] = "POST"
    fields: dict[str, str]
    expires_in: int


EpisodeTitle = Annotated[str, Field(max_length=1000)]
LanguageCode = Annotated[
    str,
    Field(
        min_length=2,
        max_length=32,
        pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
        description="BCP 47-style language code, such as pt, en-US or zh-Hant.",
    ),
]


class ImportSourceInput(BaseModel):
    type: SourceType
    url: HttpUrl | None = None
    object_key: str | None = None
    filename: EpisodeTitle | None = None
    content_type: Annotated[str, Field(max_length=255)] | None = None
    episode_guid: Annotated[str, Field(max_length=500)] | None = None
    episode_title: EpisodeTitle | None = None
    rss_url_hint: HttpUrl | None = None

    @model_validator(mode="after")
    def validate_location(self) -> ImportSourceInput:
        if self.type == SourceType.UPLOAD and not self.object_key:
            raise ValueError("object_key is required for upload imports")
        if self.type != SourceType.UPLOAD and not self.url:
            raise ValueError("url is required for URL imports")
        return self


class ImportOptions(BaseModel):
    language: LanguageCode | None = None
    diarization: bool = True
    generate_summary: bool = True
    title_override: EpisodeTitle | None = None

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        parts = value.strip().replace("_", "-").split("-")
        normalized = [parts[0].lower()]
        for part in parts[1:]:
            if len(part) == 4 and part.isalpha():
                normalized.append(part.title())
            elif (len(part) == 2 and part.isalpha()) or (len(part) == 3 and part.isdigit()):
                normalized.append(part.upper())
            else:
                normalized.append(part.lower())
        return "-".join(normalized)


class ImportRequest(BaseModel):
    source: ImportSourceInput
    options: ImportOptions = Field(default_factory=ImportOptions)


class ImportResponse(BaseModel):
    episode_id: uuid.UUID
    job_id: uuid.UUID
    status: JobStatus


class StepResponse(APIModel):
    name: str
    ordinal: int
    status: StepStatus
    attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    metrics_json: dict[str, Any]


class JobResponse(APIModel):
    id: uuid.UUID
    episode_id: uuid.UUID
    status: JobStatus
    current_step: str | None
    progress: float
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[StepResponse] = Field(default_factory=list)


class ShowBrief(APIModel):
    id: uuid.UUID
    title: str
    author: str | None
    artwork_url: str | None


class EpisodeBrief(APIModel):
    id: uuid.UUID
    title: str
    description: str | None
    canonical_url: str | None
    artwork_url: str | None
    published_at: datetime | None
    duration_ms: int | None
    language: str | None
    status: EpisodeStatus
    show: ShowBrief | None = None
    created_at: datetime


class EpisodeListResponse(BaseModel):
    items: list[EpisodeBrief]
    total: int
    active_count: int
    limit: int
    offset: int


class SpeakerResponse(APIModel):
    id: uuid.UUID
    label: str
    display_name: str | None
    confidence: float | None
    attribution_method: str | None
    confirmed_by_user: bool


class SpeakerUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=300)
    confirmed_by_user: bool = True


class SegmentResponse(APIModel):
    id: uuid.UUID
    ordinal: int
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None
    language: str | None
    speaker: SpeakerResponse | None = None


class TranscriptResponse(APIModel):
    id: uuid.UUID
    version: int
    provider: str
    model: str | None
    language: str | None
    segment_count: int
    matched_count: int
    limit: int
    query: str | None = None
    next_cursor: str | None = None
    anchor_segment_id: uuid.UUID | None = None
    segments: list[SegmentResponse]


class SummaryResponse(APIModel):
    id: uuid.UUID
    kind: str
    version: int
    provider: str
    model: str | None
    content_json: dict[str, Any]
    created_at: datetime


class EpisodeDetail(EpisodeBrief):
    speakers: list[SpeakerResponse] = Field(default_factory=list)
    summaries: list[SummaryResponse] = Field(default_factory=list)
    playback_url: str | None = None
    playback_expires_at: datetime | None = None
    latest_job: JobResponse | None = None


class PlaybackAccessResponse(BaseModel):
    playback_url: str
    expires_at: datetime
    expires_in: int


class SummaryCreateRequest(BaseModel):
    force: bool = False


class SummaryDocumentResponse(BaseModel):
    summary: EpisodeSummaryDocument
    summary_id: uuid.UUID


class ConversationCreateRequest(BaseModel):
    episode_id: uuid.UUID
    title: Annotated[str, Field(max_length=500)] | None = None


class ConversationResponse(APIModel):
    id: uuid.UUID
    episode_id: uuid.UUID | None
    title: str | None
    created_at: datetime


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=8000)


class CitationResponse(BaseModel):
    segment_id: uuid.UUID
    start_ms: int
    end_ms: int
    speaker: str | None
    quote: str


class ChatResponse(BaseModel):
    message_id: uuid.UUID
    answer: str
    citations: list[CitationResponse]
    insufficient_evidence: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    episode_id: uuid.UUID | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    episode_id: uuid.UUID
    episode_title: str
    text: str
    start_ms: int
    end_ms: int
    speaker_labels: list[str]
    score: float


class ProviderCapabilitiesResponse(BaseModel):
    providers: list[ProviderCapabilities]


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class MCPSearchResult(BaseModel):
    id: str
    title: str
    url: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPFetchResult(BaseModel):
    id: str
    title: str
    text: str
    url: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExportFormat(BaseModel):
    format: Literal["json", "markdown", "srt", "vtt"]
