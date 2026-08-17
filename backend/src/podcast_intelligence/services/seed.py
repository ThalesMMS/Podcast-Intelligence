from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from podcast_intelligence.adapters.ai.demo import DemoLanguageModel, DeterministicEmbeddingProvider
from podcast_intelligence.config import Settings
from podcast_intelligence.enums import (
    EpisodeStatus,
    JobStatus,
    StepStatus,
    TranscriptStatus,
)
from podcast_intelligence.models import (
    Episode,
    KnowledgeChunk,
    ProcessingJob,
    ProcessingStep,
    Show,
    Speaker,
    Transcript,
    TranscriptSegment,
)
from podcast_intelligence.services.chunking import build_chunks
from podcast_intelligence.services.imports import PIPELINE_STEPS
from podcast_intelligence.services.summarization import SummaryService

DEMO_EPISODE_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
DEMO_SHOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000102")

DEMO_SEGMENTS = [
    (
        "SPEAKER_00",
        "Welcome. Today we will discuss how to turn long episodes into a verifiable knowledge base without losing the conversation's temporal context.",
    ),
    (
        "SPEAKER_01",
        "The first principle is to preserve audio and transcripts as primary artifacts. Summaries and embeddings should be derived and versioned.",
    ),
    (
        "SPEAKER_00",
        "This also changes the chat design. A useful answer must point to the exact segment and let the listener return to that moment in the audio.",
    ),
    (
        "SPEAKER_01",
        "During ingestion, catalog links are not necessarily media links. The resolver must locate an authorized public source, usually the RSS enclosure.",
    ),
    (
        "SPEAKER_00",
        "For transcription, diarization and person identification are different problems. Diarization groups voices; names must come from metadata, textual evidence, or human confirmation.",
    ),
    (
        "SPEAKER_01",
        "Indexing works best when chunks respect speaker and topic changes. Vector search alone is not enough for names, acronyms, and highly specific terms.",
    ),
    (
        "SPEAKER_00",
        "That is why we use hybrid retrieval, combining semantic similarity, full-text search, and structured filters by episode, show, and workspace.",
    ),
    (
        "SPEAKER_01",
        "The complete summary is hierarchical: first we synthesize ordered blocks, then consolidate the chapters. Every important point retains the IDs of its supporting segments.",
    ),
    (
        "SPEAKER_00",
        "In production, every step must be idempotent and resumable. A language-model failure should not repeat downloading, normalization, and transcription.",
    ),
    (
        "SPEAKER_01",
        "Finally, integration with ChatGPT or Codex is safer through MCP. The backend retains control of authorization and data while the client uses explicitly described tools.",
    ),
    (
        "SPEAKER_00",
        "The conclusion is simple: traceability, provider replacement, and clear authorization boundaries are part of the product, not merely infrastructure details.",
    ),
]


def seed_demo(session: Session, settings: Settings) -> Episode:
    existing = session.scalar(select(Episode).where(Episode.id == DEMO_EPISODE_ID))
    if existing is not None:
        return existing

    workspace_id = uuid.UUID(settings.default_workspace_id)
    show = Show(
        id=DEMO_SHOW_ID,
        workspace_id=workspace_id,
        title="Architecture in Audio",
        author="Podcast Intelligence",
        description="Demo episodes about media processing and verifiable AI.",
        metadata_json={"seed": True},
    )
    episode = Episode(
        id=DEMO_EPISODE_ID,
        workspace_id=workspace_id,
        show=show,
        title="How to Build a Podcast Intelligence Tool",
        description=(
            "A demo episode about authorized ingestion, diarization, hybrid retrieval, "
            "hierarchical summaries, and MCP integration."
        ),
        published_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        duration_ms=11 * 48_000,
        language="en",
        status=EpisodeStatus.READY,
        metadata_json={"seed": True, "synthetic_audio": False},
    )
    session.add_all([show, episode])
    session.flush()

    speakers = {
        "SPEAKER_00": Speaker(
            episode_id=episode.id,
            label="SPEAKER_00",
            display_name="Host",
            confidence=1.0,
            attribution_method="seed",
            confirmed_by_user=True,
        ),
        "SPEAKER_01": Speaker(
            episode_id=episode.id,
            label="SPEAKER_01",
            display_name="Guest",
            confidence=1.0,
            attribution_method="seed",
            confirmed_by_user=True,
        ),
    }
    session.add_all(speakers.values())
    session.flush()

    transcript = Transcript(
        episode_id=episode.id,
        version=1,
        status=TranscriptStatus.READY,
        provider="demo",
        model="seed-v1",
        language="en",
        full_text=" ".join(text for _, text in DEMO_SEGMENTS),
        metadata_json={"seed": True},
    )
    session.add(transcript)
    session.flush()

    cursor = 0
    for ordinal, (speaker_label, text) in enumerate(DEMO_SEGMENTS):
        duration = max(18_000, len(text.split()) * 420)
        session.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                speaker=speakers[speaker_label],
                ordinal=ordinal,
                start_ms=cursor,
                end_ms=cursor + duration,
                text=text,
                confidence=1.0,
                language="en",
                metadata_json={"seed": True},
            )
        )
        cursor += duration + 900

    job = ProcessingJob(
        workspace_id=workspace_id,
        episode_id=episode.id,
        status=JobStatus.COMPLETED,
        progress=1.0,
        options_json={"seed": True},
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    session.add(job)
    session.flush()
    for ordinal, name in enumerate(PIPELINE_STEPS):
        session.add(
            ProcessingStep(
                job_id=job.id,
                ordinal=ordinal,
                name=name,
                status=StepStatus.COMPLETED,
                attempts=1,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                metrics_json={"seed": True},
            )
        )
    session.commit()

    loaded_transcript = session.scalar(
        select(Transcript)
        .where(Transcript.id == transcript.id)
        .options(selectinload(Transcript.segments).selectinload(TranscriptSegment.speaker))
    )
    assert loaded_transcript is not None
    chunks = build_chunks(
        loaded_transcript.segments,
        target_tokens=settings.chunk_target_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    embeddings = DeterministicEmbeddingProvider(settings.embedding_dimension)
    vectors = embeddings.embed([chunk.text for chunk in chunks])
    for chunk, vector in zip(chunks, vectors, strict=True):
        session.add(
            KnowledgeChunk(
                workspace_id=workspace_id,
                episode_id=episode.id,
                transcript_id=loaded_transcript.id,
                ordinal=chunk.ordinal,
                start_ms=chunk.start_ms,
                end_ms=chunk.end_ms,
                text=chunk.text,
                segment_ids=chunk.segment_ids,
                speaker_labels=chunk.speaker_labels,
                token_count=chunk.token_count,
                embedding_model=embeddings.model_name,
                embedding=vector,
                metadata_json={"seed": True},
            )
        )
    session.commit()
    SummaryService(session, DemoLanguageModel()).generate(workspace_id, episode.id)
    session.refresh(episode)
    return episode
