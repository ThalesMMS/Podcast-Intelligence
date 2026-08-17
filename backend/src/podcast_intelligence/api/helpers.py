from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from podcast_intelligence.domain.errors import NotFoundError
from podcast_intelligence.enums import AssetKind, TranscriptStatus
from podcast_intelligence.models import (
    Episode,
    MediaAsset,
    ProcessingJob,
    Speaker,
    Summary,
    Transcript,
)
from podcast_intelligence.schemas import EpisodeDetail, JobResponse, PlaybackAccessResponse
from podcast_intelligence.services.providers import ProviderRegistry


def get_episode_or_404(session: Session, workspace_id: uuid.UUID, episode_id: uuid.UUID) -> Episode:
    episode = session.scalar(
        select(Episode)
        .where(Episode.id == episode_id, Episode.workspace_id == workspace_id)
        .options(selectinload(Episode.show))
    )
    if episode is None:
        raise NotFoundError("Episode not found")
    return episode


def playback_access(
    playback: MediaAsset,
    registry: ProviderRegistry,
) -> PlaybackAccessResponse:
    expires_in = registry.settings.playback_url_expires_seconds
    return PlaybackAccessResponse(
        playback_url=registry.object_store.presign_get(
            playback.object_key,
            expires_seconds=expires_in,
        ),
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        expires_in=expires_in,
    )


def episode_detail(
    session: Session,
    episode: Episode,
    registry: ProviderRegistry,
) -> EpisodeDetail:
    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.episode_id == episode.id)
        .options(selectinload(ProcessingJob.steps))
        .order_by(ProcessingJob.created_at.desc(), ProcessingJob.updated_at.desc())
        .limit(1)
    )
    latest_transcript_id = session.scalar(
        select(Transcript.id)
        .where(
            Transcript.episode_id == episode.id,
            Transcript.status == TranscriptStatus.READY,
        )
        .order_by(Transcript.version.desc())
        .limit(1)
    )
    summaries = (
        list(
            session.scalars(
                select(Summary)
                .where(
                    Summary.episode_id == episode.id,
                    Summary.transcript_id == latest_transcript_id,
                )
                .order_by(
                    Summary.version.desc(),
                    Summary.created_at.desc(),
                    Summary.updated_at.desc(),
                    Summary.kind.asc(),
                )
            )
        )
        if latest_transcript_id is not None
        else []
    )
    speakers = list(
        session.scalars(
            select(Speaker)
            .where(Speaker.episode_id == episode.id)
            .order_by(Speaker.label.asc(), Speaker.id.asc())
        )
    )
    playback = session.scalar(
        select(MediaAsset).where(
            MediaAsset.episode_id == episode.id,
            MediaAsset.kind == AssetKind.PLAYBACK,
        )
    )
    access = playback_access(playback, registry) if playback else None
    return EpisodeDetail(
        id=episode.id,
        title=episode.title,
        description=episode.description,
        canonical_url=episode.canonical_url,
        artwork_url=episode.artwork_url,
        published_at=episode.published_at,
        duration_ms=episode.duration_ms,
        language=episode.language,
        status=episode.status,
        show=episode.show,
        created_at=episode.created_at,
        speakers=speakers,
        summaries=summaries,
        playback_url=access.playback_url if access else None,
        playback_expires_at=access.expires_at if access else None,
        latest_job=JobResponse.model_validate(latest_job) if latest_job else None,
    )
