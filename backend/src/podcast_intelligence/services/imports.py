from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.orm import Session

from podcast_intelligence.config import Settings
from podcast_intelligence.domain.errors import ConflictError, MediaValidationError
from podcast_intelligence.domain.ports import ObjectStore
from podcast_intelligence.enums import EpisodeStatus, JobStatus, SourceType, StepStatus
from podcast_intelligence.models import (
    Episode,
    EpisodeSource,
    JobDispatch,
    ProcessingJob,
    ProcessingStep,
)
from podcast_intelligence.schemas import (
    ImportRequest,
    ImportResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
)

PIPELINE_STEPS = (
    "resolve_source",
    "acquire_media",
    "normalize_audio",
    "transcribe",
    "index",
    "summarize",
    "finalize",
)
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(filename: str) -> str:
    name = PurePath(filename).name.strip().replace(" ", "-")
    sanitized = _SAFE_FILENAME_RE.sub("-", name).strip(".-")
    return sanitized[:240] or "upload.bin"


def enqueue_job_dispatch(session: Session, job_id: uuid.UUID) -> JobDispatch:
    """Persist or reset the durable request to publish a processing job."""
    dispatch = session.scalar(select(JobDispatch).where(JobDispatch.job_id == job_id))
    if dispatch is None:
        dispatch = JobDispatch(job_id=job_id)
        session.add(dispatch)
    else:
        dispatch.dispatched_at = None
        dispatch.dead_lettered_at = None
        dispatch.available_at = datetime.now(UTC)
        dispatch.last_error = None
        dispatch.attempts = 0
    return dispatch


class ImportService:
    def __init__(self, session: Session, object_store: ObjectStore, settings: Settings) -> None:
        self.session = session
        self.object_store = object_store
        self.settings = settings

    def initiate_upload(
        self, workspace_id: uuid.UUID, request: UploadInitiateRequest
    ) -> UploadInitiateResponse:
        upload_id = uuid.uuid4()
        filename = _safe_filename(request.filename)
        object_key = f"{workspace_id}/uploads/{upload_id}/{filename}"
        expires_in = 900
        if request.size_bytes > self.settings.max_remote_file_bytes:
            raise MediaValidationError("Upload exceeds MAX_REMOTE_FILE_BYTES")
        presigned = self.object_store.presign_post(
            object_key=object_key,
            content_type=request.content_type,
            expected_size_bytes=request.size_bytes,
            expires_seconds=expires_in,
        )
        return UploadInitiateResponse(
            object_key=object_key,
            upload_url=str(presigned["url"]),
            fields={
                str(key): str(value) for key, value in dict(presigned.get("fields") or {}).items()
            },
            expires_in=expires_in,
        )

    def create_import(self, workspace_id: uuid.UUID, request: ImportRequest) -> ImportResponse:
        if request.source.type == SourceType.UPLOAD:
            expected_prefix = f"{workspace_id}/uploads/"
            if not request.source.object_key or not request.source.object_key.startswith(
                expected_prefix
            ):
                raise ConflictError("Upload object does not belong to the active workspace")
        source_data = request.source.model_dump(mode="json", exclude_none=True)
        options_data = request.options.model_dump(mode="json", exclude_none=True)
        title = (
            request.options.title_override
            or request.source.episode_title
            or request.source.filename
            or "Import processing"
        )
        episode = Episode(
            workspace_id=workspace_id,
            title=title,
            status=EpisodeStatus.QUEUED,
            metadata_json={"import_source_type": request.source.type.value},
        )
        self.session.add(episode)
        self.session.flush()

        source = EpisodeSource(
            episode_id=episode.id,
            source_type=request.source.type,
            source_url=str(request.source.url) if request.source.url else None,
            external_id=request.source.episode_guid,
            metadata_json={
                "object_key": request.source.object_key,
                "filename": request.source.filename,
                "content_type": request.source.content_type,
            },
        )
        self.session.add(source)

        job = ProcessingJob(
            workspace_id=workspace_id,
            episode_id=episode.id,
            status=JobStatus.QUEUED,
            progress=0.0,
            options_json={"source": source_data, "options": options_data},
        )
        self.session.add(job)
        self.session.flush()
        for ordinal, name in enumerate(PIPELINE_STEPS):
            self.session.add(
                ProcessingStep(
                    job_id=job.id,
                    ordinal=ordinal,
                    name=name,
                    status=StepStatus.PENDING,
                )
            )
        enqueue_job_dispatch(self.session, job.id)
        self.session.commit()
        return ImportResponse(episode_id=episode.id, job_id=job.id, status=job.status)
