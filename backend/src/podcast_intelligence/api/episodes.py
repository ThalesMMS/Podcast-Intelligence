from __future__ import annotations

import base64
import binascii
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from podcast_intelligence.api.helpers import episode_detail, get_episode_or_404, playback_access
from podcast_intelligence.dependencies import AuthDep, RegistryDep, SessionDep
from podcast_intelligence.domain.errors import ConflictError, NotFoundError
from podcast_intelligence.enums import AssetKind, EpisodeStatus, SummaryKind, TranscriptStatus
from podcast_intelligence.models import (
    Episode,
    MediaAsset,
    Speaker,
    Summary,
    Transcript,
    TranscriptSegment,
)
from podcast_intelligence.schemas import (
    EpisodeDetail,
    EpisodeListResponse,
    PlaybackAccessResponse,
    SpeakerResponse,
    SpeakerUpdate,
    SummaryCreateRequest,
    SummaryDocumentResponse,
    SummaryResponse,
    TranscriptResponse,
)
from podcast_intelligence.services.exports import (
    export_json,
    summary_markdown,
    transcript_srt,
    transcript_vtt,
)
from podcast_intelligence.services.summarization import (
    SummaryService,
    latest_summary_for_transcript,
)

router = APIRouter(tags=["episodes"])


@router.get("/episodes", response_model=EpisodeListResponse)
def list_episodes(
    auth: AuthDep,
    session: SessionDep,
    limit: int = 50,
    offset: int = 0,
) -> EpisodeListResponse:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    total = session.scalar(
        select(func.count(Episode.id)).where(Episode.workspace_id == auth.workspace_id)
    )
    active_count = session.scalar(
        select(func.count(Episode.id)).where(
            Episode.workspace_id == auth.workspace_id,
            Episode.status.in_({EpisodeStatus.QUEUED, EpisodeStatus.PROCESSING}),
        )
    )
    episodes = list(
        session.scalars(
            select(Episode)
            .where(Episode.workspace_id == auth.workspace_id)
            .options(selectinload(Episode.show))
            .order_by(Episode.created_at.desc(), Episode.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )
    return EpisodeListResponse(
        items=episodes,
        total=int(total or 0),
        active_count=int(active_count or 0),
        limit=limit,
        offset=offset,
    )


@router.get("/episodes/{episode_id}", response_model=EpisodeDetail)
def get_episode(
    episode_id: uuid.UUID,
    auth: AuthDep,
    session: SessionDep,
    registry: RegistryDep,
) -> EpisodeDetail:
    return episode_detail(
        session,
        get_episode_or_404(session, auth.workspace_id, episode_id),
        registry,
    )


@router.get("/episodes/{episode_id}/playback", response_model=PlaybackAccessResponse)
def get_playback_access(
    episode_id: uuid.UUID,
    auth: AuthDep,
    session: SessionDep,
    registry: RegistryDep,
) -> PlaybackAccessResponse:
    playback = session.scalar(
        select(MediaAsset)
        .join(Episode, Episode.id == MediaAsset.episode_id)
        .where(
            MediaAsset.episode_id == episode_id,
            MediaAsset.kind == AssetKind.PLAYBACK,
            Episode.workspace_id == auth.workspace_id,
        )
    )
    if playback is None:
        raise NotFoundError("Playback not found")
    return playback_access(playback, registry)


def _latest_transcript(
    session: SessionDep,
    workspace_id: uuid.UUID,
    episode_id: uuid.UUID,
    *,
    load_segments: bool = True,
) -> Transcript:
    statement = (
        select(Transcript)
        .join(Episode, Episode.id == Transcript.episode_id)
        .where(
            Transcript.episode_id == episode_id,
            Episode.workspace_id == workspace_id,
            Transcript.status == TranscriptStatus.READY,
        )
        .order_by(Transcript.version.desc())
        .limit(1)
    )
    if load_segments:
        statement = statement.options(
            selectinload(Transcript.segments).selectinload(TranscriptSegment.speaker)
        )
    transcript = session.scalar(statement)
    if transcript is None:
        raise NotFoundError("Ready transcript not found")
    return transcript


def _normalize_transcript_query(query: str | None) -> str | None:
    normalized = " ".join((query or "").split()).lower()
    return normalized or None


def _encode_transcript_cursor(
    transcript_id: uuid.UUID,
    ordinal: int,
    query: str | None,
) -> str:
    payload = json.dumps(
        {"transcript_id": str(transcript_id), "ordinal": ordinal, "query": query},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def _decode_transcript_cursor(
    cursor: str,
    transcript_id: uuid.UUID,
    query: str | None,
) -> int:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        transcript_id_value = payload["transcript_id"]
        if not isinstance(transcript_id_value, str):
            raise ValueError
        cursor_transcript_id = uuid.UUID(transcript_id_value)
        ordinal = payload["ordinal"]
        if (
            cursor_transcript_id != transcript_id
            or payload.get("query") != query
            or not isinstance(ordinal, int)
            or isinstance(ordinal, bool)
            or ordinal < -1
        ):
            raise ValueError
        return ordinal
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid transcript cursor") from exc


def _transcript_search_filter(query: str) -> ColumnElement[bool]:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return or_(
        func.lower(TranscriptSegment.text).like(pattern, escape="\\"),
        func.lower(Speaker.label).like(pattern, escape="\\"),
        func.lower(Speaker.display_name).like(pattern, escape="\\"),
    )


@router.get("/episodes/{episode_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    episode_id: uuid.UUID,
    auth: AuthDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    at_ms: Annotated[int | None, Query(ge=0)] = None,
) -> TranscriptResponse:
    if cursor is not None and at_ms is not None:
        raise HTTPException(status_code=400, detail="cursor and at_ms cannot be combined")

    transcript = _latest_transcript(
        session,
        auth.workspace_id,
        episode_id,
        load_segments=False,
    )
    normalized_query = _normalize_transcript_query(q)
    if normalized_query is not None and at_ms is not None:
        raise HTTPException(status_code=400, detail="q and at_ms cannot be combined")

    segment_count = int(
        session.scalar(
            select(func.count(TranscriptSegment.id)).where(
                TranscriptSegment.transcript_id == transcript.id
            )
        )
        or 0
    )
    conditions = [TranscriptSegment.transcript_id == transcript.id]
    search_filter = None
    if normalized_query is not None:
        search_filter = _transcript_search_filter(normalized_query)
        conditions.append(search_filter)

    matched_count = segment_count
    if search_filter is not None:
        matched_count = int(
            session.scalar(
                select(func.count(TranscriptSegment.id))
                .outerjoin(Speaker, Speaker.id == TranscriptSegment.speaker_id)
                .where(*conditions)
            )
            or 0
        )

    after_ordinal = -1
    anchor_segment_id = None
    if cursor is not None:
        after_ordinal = _decode_transcript_cursor(cursor, transcript.id, normalized_query)
    elif at_ms is not None:
        anchor = session.execute(
            select(TranscriptSegment.id, TranscriptSegment.ordinal)
            .where(
                TranscriptSegment.transcript_id == transcript.id,
                TranscriptSegment.start_ms <= at_ms,
            )
            .order_by(TranscriptSegment.start_ms.desc(), TranscriptSegment.ordinal.desc())
            .limit(1)
        ).first()
        if anchor is None:
            anchor = session.execute(
                select(TranscriptSegment.id, TranscriptSegment.ordinal)
                .where(TranscriptSegment.transcript_id == transcript.id)
                .order_by(TranscriptSegment.ordinal.asc())
                .limit(1)
            ).first()
        if anchor is not None:
            anchor_segment_id, anchor_ordinal = anchor
            preceding_ordinals = list(
                session.scalars(
                    select(TranscriptSegment.ordinal)
                    .where(
                        TranscriptSegment.transcript_id == transcript.id,
                        TranscriptSegment.ordinal < anchor_ordinal,
                    )
                    .order_by(TranscriptSegment.ordinal.desc())
                    .limit(limit // 2)
                )
            )
            if preceding_ordinals:
                after_ordinal = min(preceding_ordinals) - 1
            else:
                after_ordinal = anchor_ordinal - 1

    statement = (
        select(TranscriptSegment)
        .where(*conditions, TranscriptSegment.ordinal > after_ordinal)
        .options(selectinload(TranscriptSegment.speaker))
        .order_by(TranscriptSegment.ordinal.asc(), TranscriptSegment.id.asc())
        .limit(limit + 1)
    )
    if search_filter is not None:
        statement = statement.outerjoin(Speaker, Speaker.id == TranscriptSegment.speaker_id)
    page = list(session.scalars(statement))
    has_more = len(page) > limit
    segments = page[:limit]
    next_cursor = None
    if has_more and segments:
        next_cursor = _encode_transcript_cursor(
            transcript.id,
            segments[-1].ordinal,
            normalized_query,
        )

    return TranscriptResponse(
        id=transcript.id,
        version=transcript.version,
        provider=transcript.provider,
        model=transcript.model,
        language=transcript.language,
        segment_count=segment_count,
        matched_count=matched_count,
        limit=limit,
        query=normalized_query,
        next_cursor=next_cursor,
        anchor_segment_id=anchor_segment_id,
        segments=segments,
    )


@router.patch("/episodes/{episode_id}/speakers/{speaker_id}", response_model=SpeakerResponse)
def update_speaker(
    episode_id: uuid.UUID,
    speaker_id: uuid.UUID,
    request: SpeakerUpdate,
    auth: AuthDep,
    session: SessionDep,
) -> Speaker:
    speaker = session.scalar(
        select(Speaker)
        .join(Episode, Episode.id == Speaker.episode_id)
        .where(
            Speaker.id == speaker_id,
            Speaker.episode_id == episode_id,
            Episode.workspace_id == auth.workspace_id,
        )
    )
    if speaker is None:
        raise NotFoundError("Speaker not found")
    speaker.display_name = request.display_name
    speaker.confirmed_by_user = request.confirmed_by_user
    speaker.attribution_method = "user_confirmation"
    speaker.confidence = 1.0
    session.commit()
    session.refresh(speaker)
    return speaker


@router.get("/episodes/{episode_id}/summaries", response_model=list[SummaryResponse])
def list_summaries(
    episode_id: uuid.UUID,
    auth: AuthDep,
    session: SessionDep,
) -> list[Summary]:
    try:
        transcript = _latest_transcript(
            session,
            auth.workspace_id,
            episode_id,
            load_segments=False,
        )
    except NotFoundError:
        episode_exists = session.scalar(
            select(Episode.id).where(
                Episode.id == episode_id,
                Episode.workspace_id == auth.workspace_id,
            )
        )
        if episode_exists is None:
            raise NotFoundError("Episode not found") from None
        return []
    return list(
        session.scalars(
            select(Summary)
            .where(
                Summary.episode_id == episode_id,
                Summary.transcript_id == transcript.id,
            )
            .order_by(
                Summary.version.desc(),
                Summary.created_at.desc(),
                Summary.id.desc(),
            )
        )
    )


@router.post(
    "/episodes/{episode_id}/summaries",
    response_model=SummaryDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_summary(
    episode_id: uuid.UUID,
    request: SummaryCreateRequest,
    auth: AuthDep,
    session: SessionDep,
    registry: RegistryDep,
) -> SummaryDocumentResponse:
    summary = SummaryService(session, registry.llm).generate(
        auth.workspace_id, episode_id, force=request.force
    )
    return SummaryDocumentResponse(summary=summary.content_json, summary_id=summary.id)


@router.get("/episodes/{episode_id}/exports/{format_name}")
def export_episode(
    episode_id: uuid.UUID,
    format_name: str,
    auth: AuthDep,
    session: SessionDep,
) -> Response:
    episode = get_episode_or_404(session, auth.workspace_id, episode_id)
    transcript = _latest_transcript(session, auth.workspace_id, episode_id)
    filename_base = f"episode-{episode.id}"
    if format_name == "srt":
        return Response(
            transcript_srt(transcript.segments),
            media_type="application/x-subrip",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.srt"'},
        )
    if format_name == "vtt":
        return Response(
            transcript_vtt(transcript.segments),
            media_type="text/vtt",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.vtt"'},
        )

    summary = latest_summary_for_transcript(
        session,
        episode_id,
        transcript.id,
        kind=SummaryKind.DETAILED,
    )
    if summary is None:
        raise ConflictError("A summary is required for this export format")
    if format_name == "markdown":
        return Response(
            summary_markdown(episode.title, summary),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.md"'},
        )
    if format_name == "json":
        payload = {
            "episode": {
                "id": str(episode.id),
                "title": episode.title,
                "canonical_url": episode.canonical_url,
                "published_at": episode.published_at,
                "duration_ms": episode.duration_ms,
            },
            "summary": summary.content_json,
            "transcript": [
                {
                    "id": str(segment.id),
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "speaker": (
                        segment.speaker.display_name or segment.speaker.label
                        if segment.speaker
                        else None
                    ),
                    "text": segment.text,
                }
                for segment in transcript.segments
            ],
        }
        return Response(
            export_json(payload),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.json"'},
        )
    raise NotFoundError("Unsupported export format")
