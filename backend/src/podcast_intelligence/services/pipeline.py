from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from podcast_intelligence.domain.errors import (
    JobCancelledError,
    MediaValidationError,
    NotFoundError,
    SourceResolutionError,
)
from podcast_intelligence.domain.types import (
    TranscriptionResult,
    TranscriptReference,
    TranscriptSegmentData,
)
from podcast_intelligence.enums import (
    AssetKind,
    EpisodeStatus,
    JobStatus,
    ProviderKind,
    SourceType,
    StepStatus,
    TranscriptStatus,
)
from podcast_intelligence.models import (
    EpisodeSource,
    KnowledgeChunk,
    MediaAsset,
    ProcessingJob,
    ProcessingStep,
    ProviderRun,
    Show,
    Speaker,
    Transcript,
    TranscriptSegment,
)
from podcast_intelligence.services.chunking import build_chunks
from podcast_intelligence.services.imports import PIPELINE_STEPS
from podcast_intelligence.services.providers import ProviderRegistry
from podcast_intelligence.services.summarization import SummaryService

StepCallable = Callable[[ProcessingJob], dict[str, Any]]


def _validated_upload_head(head: dict[str, Any], max_size_bytes: int) -> tuple[int, str | None]:
    size_bytes = int(str(head.get("content_length") or 0))
    if size_bytes <= 0 or size_bytes > max_size_bytes:
        raise MediaValidationError("Uploaded media is empty or exceeds MAX_REMOTE_FILE_BYTES")
    metadata = dict(head.get("metadata") or {})
    raw_expected_size = metadata.get("expected-size")
    try:
        expected_size = int(str(raw_expected_size))
    except (TypeError, ValueError) as exc:
        raise MediaValidationError("Uploaded media is missing signed size metadata") from exc
    if expected_size != size_bytes:
        raise MediaValidationError("Uploaded media size does not match the signed upload policy")
    content_type = head.get("content_type")
    return size_bytes, str(content_type) if content_type else None


class JobPipeline:
    def __init__(self, session: Session, registry: ProviderRegistry) -> None:
        self.session = session
        self.registry = registry
        self.settings = registry.settings
        self.settings.processing_temp_dir.mkdir(parents=True, exist_ok=True)

    def run(self, job_id: uuid.UUID) -> None:
        job = self._job(job_id)
        if job.status == JobStatus.COMPLETED:
            return
        if job.status == JobStatus.CANCELLED:
            raise JobCancelledError("Job was cancelled before processing started")

        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or datetime.now(UTC)
        job.error_code = None
        job.error_message = None
        job.episode.status = EpisodeStatus.PROCESSING
        self.session.commit()

        handlers: dict[str, StepCallable] = {
            "resolve_source": self._resolve_source,
            "acquire_media": self._acquire_media,
            "normalize_audio": self._normalize_audio,
            "transcribe": self._transcribe,
            "index": self._index,
            "summarize": self._summarize,
            "finalize": self._finalize,
        }
        try:
            for step_name in PIPELINE_STEPS:
                job = self._job(job_id)
                if job.status == JobStatus.CANCELLED:
                    raise JobCancelledError("Job was cancelled")
                options = job.options_json.get("options") or {}
                if step_name == "summarize" and options.get("generate_summary", True) is False:
                    self._skip_step(job, step_name, "Summary generation disabled")
                    continue
                self._execute_step(job, step_name, handlers[step_name])
        except Exception as exc:
            self._mark_failed(job_id, exc)
            raise

        job = self._job(job_id)
        job.status = JobStatus.COMPLETED
        job.current_step = None
        job.progress = 1.0
        job.completed_at = datetime.now(UTC)
        job.episode.status = EpisodeStatus.READY
        self.session.commit()

    def _job(self, job_id: uuid.UUID) -> ProcessingJob:
        job = self.session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(ProcessingJob.episode),
                selectinload(ProcessingJob.steps),
            )
        )
        if job is None:
            raise NotFoundError("Processing job not found")
        return job

    def _step(self, job_id: uuid.UUID, name: str) -> ProcessingStep:
        step = self.session.scalar(
            select(ProcessingStep).where(
                ProcessingStep.job_id == job_id,
                ProcessingStep.name == name,
            )
        )
        if step is None:
            raise RuntimeError(f"Pipeline step is missing: {name}")
        return step

    def _execute_step(self, job: ProcessingJob, name: str, handler: StepCallable) -> None:
        step = self._step(job.id, name)
        if step.status in {StepStatus.COMPLETED, StepStatus.SKIPPED}:
            return
        step.status = StepStatus.RUNNING
        step.attempts += 1
        step.started_at = datetime.now(UTC)
        step.completed_at = None
        step.error_message = None
        job.status = JobStatus.RUNNING
        job.current_step = name
        job.progress = step.ordinal / len(PIPELINE_STEPS)
        self.session.commit()

        started = time.perf_counter()
        metrics = handler(self._job(job.id))
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        refreshed_job = self._job(job.id)
        if refreshed_job.status == JobStatus.CANCELLED:
            raise JobCancelledError(f"Job was cancelled during step {name}")
        step = self._step(job.id, name)
        step.status = StepStatus.COMPLETED
        step.completed_at = datetime.now(UTC)
        step.metrics_json = {**metrics, "elapsed_ms": elapsed_ms}
        refreshed_job.progress = (step.ordinal + 1) / len(PIPELINE_STEPS)
        self.session.commit()

    def _skip_step(self, job: ProcessingJob, name: str, reason: str) -> None:
        step = self._step(job.id, name)
        if step.status == StepStatus.COMPLETED:
            return
        step.status = StepStatus.SKIPPED
        step.completed_at = datetime.now(UTC)
        step.metrics_json = {"reason": reason}
        job.current_step = name
        job.progress = (step.ordinal + 1) / len(PIPELINE_STEPS)
        self.session.commit()

    def _mark_failed(self, job_id: uuid.UUID, exc: Exception) -> None:
        self.session.rollback()
        job = self._job(job_id)
        if isinstance(exc, JobCancelledError):
            job.status = JobStatus.CANCELLED
            job.episode.status = (
                EpisodeStatus.READY
                if self._latest_ready_transcript(job.episode_id) is not None
                else EpisodeStatus.DRAFT
            )
        else:
            job.status = JobStatus.FAILED
            job.episode.status = EpisodeStatus.FAILED
        job.error_code = getattr(exc, "code", "pipeline_failed")
        job.error_message = str(exc)[:8000]
        job.completed_at = datetime.now(UTC)
        if job.current_step:
            step = self._step(job.id, job.current_step)
            if step.status == StepStatus.RUNNING:
                step.status = StepStatus.FAILED
                step.completed_at = datetime.now(UTC)
                step.error_message = str(exc)[:8000]
        self.session.commit()

    def _episode_source(self, job: ProcessingJob) -> EpisodeSource:
        source = self.session.scalar(
            select(EpisodeSource).where(EpisodeSource.episode_id == job.episode_id)
        )
        if source is None:
            raise RuntimeError("Episode source is missing")
        return source

    def _asset(self, episode_id: uuid.UUID, kind: AssetKind) -> MediaAsset | None:
        return self.session.scalar(
            select(MediaAsset).where(
                MediaAsset.episode_id == episode_id,
                MediaAsset.kind == kind,
            )
        )

    def _upsert_asset(
        self,
        episode_id: uuid.UUID,
        kind: AssetKind,
        *,
        object_key: str,
        mime_type: str | None,
        size_bytes: int | None,
        sha256: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MediaAsset:
        asset = self._asset(episode_id, kind)
        if asset is None:
            asset = MediaAsset(episode_id=episode_id, kind=kind, object_key=object_key)
            self.session.add(asset)
        asset.object_key = object_key
        asset.mime_type = mime_type
        asset.size_bytes = size_bytes
        asset.sha256 = sha256
        asset.duration_ms = duration_ms
        asset.metadata_json = metadata or {}
        self.session.flush()
        return asset

    def _resolve_source(self, job: ProcessingJob) -> dict[str, Any]:
        source_input = dict(job.options_json.get("source") or {})
        source_type = SourceType(source_input["type"])
        source = self._episode_source(job)
        if source_type == SourceType.UPLOAD:
            object_key = str(source_input["object_key"])
            head = self.registry.object_store.head(object_key)
            size_bytes, content_type = _validated_upload_head(
                head, self.settings.max_remote_file_bytes
            )
            source.metadata_json = {
                **source.metadata_json,
                "object_key": object_key,
                "size_bytes": size_bytes,
                "content_type": content_type or source_input.get("content_type"),
            }
            if job.episode.title == "Import processing":
                job.episode.title = str(source_input.get("filename") or "Uploaded audio")
            self.session.commit()
            return {"source_type": source_type.value, "object_key": object_key}

        resolver = self.registry.resolver_for(source_type)
        resolved = resolver.resolve(
            str(source_input["url"]),
            episode_guid=source_input.get("episode_guid"),
            episode_title=source_input.get("episode_title"),
            rss_url_hint=source_input.get("rss_url_hint"),
        )
        episode = job.episode
        options = job.options_json.get("options") or {}
        episode.title = str(options.get("title_override") or resolved.title)
        episode.description = resolved.description
        episode.canonical_url = resolved.canonical_url
        episode.artwork_url = resolved.artwork_url or resolved.show_artwork_url
        episode.published_at = resolved.published_at
        episode.duration_ms = resolved.duration_ms
        episode.language = resolved.language or options.get("language")
        episode.metadata_json = {**episode.metadata_json, **resolved.metadata}

        if resolved.show_title:
            show = None
            if resolved.rss_url:
                show = self.session.scalar(
                    select(Show).where(
                        Show.workspace_id == job.workspace_id,
                        Show.rss_url == resolved.rss_url,
                    )
                )
            if show is None:
                show = Show(
                    workspace_id=job.workspace_id,
                    title=resolved.show_title,
                    rss_url=resolved.rss_url,
                )
                self.session.add(show)
                self.session.flush()
            show.title = resolved.show_title
            show.author = resolved.show_author
            show.description = resolved.show_description
            show.artwork_url = resolved.show_artwork_url
            show.metadata_json = {"resolved_from": source_type.value}
            episode.show_id = show.id

        source.external_id = resolved.external_id
        source.resolved_media_url = resolved.media_url
        source.resolution_confidence = resolved.resolution_confidence
        source.metadata_json = {
            **source.metadata_json,
            **resolved.metadata,
            "rss_url": resolved.rss_url,
            "media_mime_type": resolved.media_mime_type,
            "published_transcripts": [
                item.model_dump(mode="json") for item in resolved.published_transcripts
            ],
        }
        job.options_json = {
            **job.options_json,
            "resolved": resolved.model_dump(mode="json"),
        }
        self.session.commit()
        return {
            "source_type": source_type.value,
            "resolution_confidence": resolved.resolution_confidence,
            "published_transcripts": len(resolved.published_transcripts),
        }

    def _acquire_media(self, job: ProcessingJob) -> dict[str, Any]:
        existing = self._asset(job.episode_id, AssetKind.ORIGINAL)
        if existing is not None:
            return {"reused": True, "size_bytes": existing.size_bytes}

        source_input = dict(job.options_json.get("source") or {})
        source_type = SourceType(source_input["type"])
        source = self._episode_source(job)
        if source_type == SourceType.UPLOAD:
            object_key = str(source_input["object_key"])
            head = self.registry.object_store.head(object_key)
            size_bytes, content_type = _validated_upload_head(
                head, self.settings.max_remote_file_bytes
            )
            self._upsert_asset(
                job.episode_id,
                AssetKind.ORIGINAL,
                object_key=object_key,
                mime_type=content_type or source_input.get("content_type"),
                size_bytes=size_bytes,
                metadata={"upload": True, "etag": head.get("etag")},
            )
            self.session.commit()
            return {"reused_upload": True, "size_bytes": head.get("content_length")}

        if not source.resolved_media_url:
            raise RuntimeError("Source resolution did not produce an authorized media URL")
        with TemporaryDirectory(dir=self.settings.processing_temp_dir) as temporary_directory:
            downloaded = self.registry.http.download(
                source.resolved_media_url, Path(temporary_directory)
            )
            object_key = f"{job.workspace_id}/episodes/{job.episode_id}/original/source-media"
            self.registry.object_store.upload_file(
                downloaded.path, object_key, downloaded.content_type
            )
            self._upsert_asset(
                job.episode_id,
                AssetKind.ORIGINAL,
                object_key=object_key,
                mime_type=downloaded.content_type,
                size_bytes=downloaded.size_bytes,
                sha256=downloaded.sha256,
                metadata={"final_url": downloaded.final_url},
            )
            self.session.commit()
            return {
                "size_bytes": downloaded.size_bytes,
                "sha256": downloaded.sha256,
                "final_url": downloaded.final_url,
            }

    def _normalize_audio(self, job: ProcessingJob) -> dict[str, Any]:
        processing = self._asset(job.episode_id, AssetKind.PROCESSING)
        playback = self._asset(job.episode_id, AssetKind.PLAYBACK)
        if processing is not None and playback is not None:
            return {"reused": True, "duration_ms": processing.duration_ms}
        original = self._asset(job.episode_id, AssetKind.ORIGINAL)
        if original is None:
            raise RuntimeError("Original media asset is missing")

        with TemporaryDirectory(dir=self.settings.processing_temp_dir) as temporary_directory:
            directory = Path(temporary_directory)
            source_path = directory / "original-media"
            processing_path = directory / "processing.wav"
            playback_path = directory / "playback.m4a"
            self.registry.object_store.download_file(original.object_key, source_path)
            metadata = self.registry.media.normalize(source_path, processing_path)
            self.registry.media.create_playback(source_path, playback_path)

            processing_key = (
                f"{job.workspace_id}/episodes/{job.episode_id}/processing/audio-16khz-mono.wav"
            )
            playback_key = f"{job.workspace_id}/episodes/{job.episode_id}/playback/audio.m4a"
            self.registry.object_store.upload_file(processing_path, processing_key, "audio/wav")
            self.registry.object_store.upload_file(playback_path, playback_key, "audio/mp4")
            self._upsert_asset(
                job.episode_id,
                AssetKind.PROCESSING,
                object_key=processing_key,
                mime_type="audio/wav",
                size_bytes=processing_path.stat().st_size,
                sha256=self._sha256(processing_path),
                duration_ms=metadata.duration_ms,
                metadata=metadata.model_dump(mode="json"),
            )
            self._upsert_asset(
                job.episode_id,
                AssetKind.PLAYBACK,
                object_key=playback_key,
                mime_type="audio/mp4",
                size_bytes=playback_path.stat().st_size,
                sha256=self._sha256(playback_path),
                duration_ms=metadata.duration_ms,
            )
            job.episode.duration_ms = metadata.duration_ms
            self.session.commit()
            return {
                "duration_ms": metadata.duration_ms,
                "sample_rate": metadata.sample_rate,
                "channels": metadata.channels,
            }

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def _latest_ready_transcript(self, episode_id: uuid.UUID) -> Transcript | None:
        return self.session.scalar(
            select(Transcript)
            .where(
                Transcript.episode_id == episode_id,
                Transcript.status == TranscriptStatus.READY,
            )
            .order_by(Transcript.version.desc())
            .limit(1)
        )

    def _record_run(
        self,
        job: ProcessingJob,
        kind: ProviderKind,
        provider: str,
        model: str | None,
        *,
        latency_ms: int,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            ProviderRun(
                job_id=job.id,
                kind=kind,
                provider=provider,
                model=model,
                request_id=request_id,
                latency_ms=latency_ms,
                metadata_json=metadata or {},
            )
        )

    def _transcribe(self, job: ProcessingJob) -> dict[str, Any]:
        existing = self._latest_ready_transcript(job.episode_id)
        if existing is not None:
            segment_count = self.session.scalar(
                select(func.count(TranscriptSegment.id)).where(
                    TranscriptSegment.transcript_id == existing.id
                )
            )
            return {"reused": True, "transcript_id": str(existing.id), "segments": segment_count}
        processing = self._asset(job.episode_id, AssetKind.PROCESSING)
        if processing is None:
            raise RuntimeError("Normalized processing asset is missing")
        options = job.options_json.get("options") or {}
        language = options.get("language") or job.episode.language
        source = self._episode_source(job)
        raw_references = source.metadata_json.get("published_transcripts") or []
        references: list[TranscriptReference] = []
        for raw_reference in raw_references:
            try:
                references.append(TranscriptReference.model_validate(raw_reference))
            except (TypeError, ValueError):
                continue

        started = time.perf_counter()
        result: TranscriptionResult | None = None
        published_error: str | None = None
        if references:
            try:
                result = self.registry.published_transcripts.load_first(
                    references,
                    language=language,
                    duration_ms=processing.duration_ms,
                )
            except SourceResolutionError as exc:
                published_error = str(exc)[:2000]

        if result is None:
            with TemporaryDirectory(dir=self.settings.processing_temp_dir) as temporary_directory:
                audio_path = Path(temporary_directory) / "audio.wav"
                self.registry.object_store.download_file(processing.object_key, audio_path)
                result = self.registry.transcriber.transcribe(
                    audio_path,
                    language=language,
                )
        latency_ms = round((time.perf_counter() - started) * 1000)
        if published_error:
            result.metadata = {**result.metadata, "published_transcript_error": published_error}

        if not result.segments and result.text:
            result.segments = [
                TranscriptSegmentData(
                    ordinal=0,
                    start_ms=0,
                    end_ms=processing.duration_ms or 0,
                    text=result.text,
                    speaker_label="SPEAKER_UNKNOWN",
                    language=result.language,
                )
            ]
        max_version = self.session.scalar(
            select(func.max(Transcript.version)).where(Transcript.episode_id == job.episode_id)
        )
        transcript = Transcript(
            episode_id=job.episode_id,
            version=int(max_version or 0) + 1,
            status=TranscriptStatus.PROCESSING,
            provider=result.provider,
            model=result.model,
            language=result.language,
            full_text=result.text,
            metadata_json=result.metadata,
        )
        self.session.add(transcript)
        self.session.flush()

        speakers: dict[str, Speaker] = {}
        for segment_data in result.segments:
            label = (segment_data.speaker_label or "SPEAKER_UNKNOWN")[:100]
            if label not in speakers:
                speaker = self.session.scalar(
                    select(Speaker).where(
                        Speaker.episode_id == job.episode_id,
                        Speaker.label == label,
                    )
                )
                if speaker is None:
                    speaker_name = segment_data.metadata.get("speaker_name")
                    speaker = Speaker(
                        episode_id=job.episode_id,
                        label=label,
                        display_name=str(speaker_name)[:300] if speaker_name else None,
                        confidence=segment_data.confidence,
                        attribution_method=(
                            "published_transcript"
                            if result.provider == "published_transcript"
                            else "provider_diarization"
                        ),
                    )
                    self.session.add(speaker)
                    self.session.flush()
                speakers[label] = speaker
            self.session.add(
                TranscriptSegment(
                    transcript_id=transcript.id,
                    speaker_id=speakers[label].id,
                    ordinal=segment_data.ordinal,
                    start_ms=segment_data.start_ms,
                    end_ms=segment_data.end_ms,
                    text=segment_data.text,
                    confidence=segment_data.confidence,
                    language=segment_data.language or result.language,
                    metadata_json=segment_data.metadata,
                )
            )
        transcript.status = TranscriptStatus.READY
        self._record_run(
            job,
            ProviderKind.TRANSCRIPTION,
            result.provider,
            result.model,
            latency_ms=latency_ms,
            request_id=result.request_id,
            metadata={"segments": len(result.segments), **result.metadata},
        )
        job.episode.language = result.language or job.episode.language
        self.session.commit()
        return {
            "transcript_id": str(transcript.id),
            "segments": len(result.segments),
            "provider": result.provider,
            "model": result.model,
        }

    def _index(self, job: ProcessingJob) -> dict[str, Any]:
        transcript = self.session.scalar(
            select(Transcript)
            .where(
                Transcript.episode_id == job.episode_id,
                Transcript.status == TranscriptStatus.READY,
            )
            .options(selectinload(Transcript.segments).selectinload(TranscriptSegment.speaker))
            .order_by(Transcript.version.desc())
            .limit(1)
        )
        if transcript is None:
            raise RuntimeError("Ready transcript is missing")
        existing = self.session.scalar(
            select(func.count(KnowledgeChunk.id)).where(
                KnowledgeChunk.transcript_id == transcript.id,
                KnowledgeChunk.embedding_model == self.registry.embeddings.model_name,
            )
        )
        if existing:
            return {"reused": True, "chunks": int(existing)}

        self.session.execute(
            delete(KnowledgeChunk).where(KnowledgeChunk.transcript_id == transcript.id)
        )
        chunk_inputs = build_chunks(
            transcript.segments,
            target_tokens=self.settings.chunk_target_tokens,
            overlap_tokens=self.settings.chunk_overlap_tokens,
        )
        if not chunk_inputs:
            raise RuntimeError("The transcript produced no indexable chunks")
        started = time.perf_counter()
        vectors: list[list[float]] = []
        batch_size = self.settings.embedding_batch_size
        for index in range(0, len(chunk_inputs), batch_size):
            batch = chunk_inputs[index : index + batch_size]
            vectors.extend(self.registry.embeddings.embed([item.text for item in batch]))
        latency_ms = round((time.perf_counter() - started) * 1000)
        if len(vectors) != len(chunk_inputs):
            raise RuntimeError("Embedding provider returned an unexpected number of vectors")
        for chunk, vector in zip(chunk_inputs, vectors, strict=True):
            self.session.add(
                KnowledgeChunk(
                    workspace_id=job.workspace_id,
                    episode_id=job.episode_id,
                    transcript_id=transcript.id,
                    ordinal=chunk.ordinal,
                    start_ms=chunk.start_ms,
                    end_ms=chunk.end_ms,
                    text=chunk.text,
                    segment_ids=chunk.segment_ids,
                    speaker_labels=chunk.speaker_labels,
                    token_count=chunk.token_count,
                    embedding_model=self.registry.embeddings.model_name,
                    embedding=vector,
                    metadata_json={"chunking": "speaker-aware-v1"},
                )
            )
        self._record_run(
            job,
            ProviderKind.EMBEDDING,
            self.registry.embeddings.provider_name,
            self.registry.embeddings.model_name,
            latency_ms=latency_ms,
            metadata={"chunks": len(chunk_inputs), "dimension": self.registry.embeddings.dimension},
        )
        self.session.commit()
        return {
            "chunks": len(chunk_inputs),
            "provider": self.registry.embeddings.provider_name,
            "model": self.registry.embeddings.model_name,
        }

    def _summarize(self, job: ProcessingJob) -> dict[str, Any]:
        started = time.perf_counter()
        summary = SummaryService(self.session, self.registry.llm).generate(
            job.workspace_id, job.episode_id, force=False
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._record_run(
            job,
            ProviderKind.LLM,
            self.registry.llm.provider_name,
            self.registry.llm.model_name,
            latency_ms=latency_ms,
            metadata={"summary_id": str(summary.id), "prompt_version": summary.prompt_version},
        )
        self.session.commit()
        return {
            "summary_id": str(summary.id),
            "provider": summary.provider,
            "model": summary.model,
        }

    def _finalize(self, job: ProcessingJob) -> dict[str, Any]:
        job.episode.status = EpisodeStatus.READY
        self.session.commit()
        return {"episode_status": EpisodeStatus.READY.value}
