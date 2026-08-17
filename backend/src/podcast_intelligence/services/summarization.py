from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from podcast_intelligence.database import summary_generation_transaction
from podcast_intelligence.domain.errors import ConflictError, NotFoundError
from podcast_intelligence.domain.ports import LanguageModel
from podcast_intelligence.domain.types import EpisodeSummaryDocument, SectionDigest
from podcast_intelligence.enums import SummaryKind, TranscriptStatus
from podcast_intelligence.models import Episode, KnowledgeChunk, Summary, Transcript

_MAX_TRANSCRIPT_CHANGE_ATTEMPTS = 5


def format_timestamp(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def latest_summary_for_transcript(
    session: Session,
    episode_id: uuid.UUID,
    transcript_id: uuid.UUID,
    *,
    kind: SummaryKind = SummaryKind.DETAILED,
) -> Summary | None:
    return session.scalar(
        select(Summary)
        .where(
            Summary.episode_id == episode_id,
            Summary.transcript_id == transcript_id,
            Summary.kind == kind,
        )
        .order_by(
            Summary.version.desc(),
            Summary.created_at.desc(),
            Summary.id.desc(),
        )
        .limit(1)
    )


class SummaryService:
    def __init__(self, session: Session, llm: LanguageModel) -> None:
        self.session = session
        self.llm = llm

    def _latest_transcript(self, episode_id: uuid.UUID) -> Transcript:
        transcript = self.session.scalar(
            select(Transcript)
            .where(
                Transcript.episode_id == episode_id,
                Transcript.status == TranscriptStatus.READY,
            )
            .order_by(Transcript.version.desc())
            .limit(1)
        )
        if transcript is None:
            raise ConflictError("The episode does not have a ready transcript")
        return transcript

    @staticmethod
    def _groups(
        chunks: Sequence[KnowledgeChunk], group_size: int = 5
    ) -> list[list[KnowledgeChunk]]:
        return [
            list(chunks[index : index + group_size]) for index in range(0, len(chunks), group_size)
        ]

    @staticmethod
    def _validated_ids(candidate_ids: Sequence[str], allowed: set[str]) -> list[str]:
        return list(dict.fromkeys(item for item in candidate_ids if item in allowed))

    def _generate_for_transcript(
        self,
        episode: Episode,
        transcript: Transcript,
        *,
        force: bool,
    ) -> Summary:
        existing = latest_summary_for_transcript(
            self.session,
            episode.id,
            transcript.id,
        )
        if existing is not None and not force:
            return existing

        chunks = list(
            self.session.scalars(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.episode_id == episode.id,
                    KnowledgeChunk.transcript_id == transcript.id,
                )
                .order_by(KnowledgeChunk.ordinal)
            )
        )
        if not chunks:
            raise ConflictError("The episode transcript has not been indexed")

        digests: list[SectionDigest] = []
        all_allowed_ids: set[str] = set()
        for group_number, group in enumerate(self._groups(chunks), start=1):
            available_ids = list(
                dict.fromkeys(segment_id for chunk in group for segment_id in chunk.segment_ids)
            )
            allowed = set(available_ids)
            all_allowed_ids.update(allowed)
            section_title = f"Parte {group_number} · {format_timestamp(group[0].start_ms)}"
            transcript_text = "\n\n".join(chunk.text for chunk in group)
            digest = self.llm.summarize_section(
                episode.title,
                section_title,
                transcript_text,
                available_ids,
            )
            digest.title = digest.title.strip() or section_title
            digest.start_ms = group[0].start_ms
            digest.end_ms = group[-1].end_ms
            digest.supporting_segment_ids = (
                self._validated_ids(digest.supporting_segment_ids, allowed) or available_ids[:8]
            )
            digests.append(digest)

        document: EpisodeSummaryDocument = self.llm.synthesize_summary(episode.title, digests)
        for chapter in document.chapters:
            chapter.supporting_segment_ids = self._validated_ids(
                chapter.supporting_segment_ids, all_allowed_ids
            )
        for point in [*document.key_takeaways, *document.open_questions]:
            point.supporting_segment_ids = self._validated_ids(
                point.supporting_segment_ids, all_allowed_ids
            )

        max_version = self.session.scalar(
            select(func.max(Summary.version)).where(
                Summary.episode_id == episode.id,
                Summary.transcript_id == transcript.id,
                Summary.kind == SummaryKind.DETAILED,
            )
        )
        summary = Summary(
            episode_id=episode.id,
            transcript_id=transcript.id,
            kind=SummaryKind.DETAILED,
            version=int(max_version or 0) + 1,
            provider=self.llm.provider_name,
            model=self.llm.model_name,
            content_json=document.model_dump(mode="json"),
            prompt_version="hierarchical-v1",
        )
        self.session.add(summary)
        self.session.flush()
        self.session.refresh(summary)
        return summary

    def generate(
        self,
        workspace_id: uuid.UUID,
        episode_id: uuid.UUID,
        *,
        force: bool = False,
    ) -> Summary:
        episode = self.session.scalar(
            select(Episode).where(
                Episode.id == episode_id,
                Episode.workspace_id == workspace_id,
            )
        )
        if episode is None:
            raise NotFoundError("Episode not found")

        for _ in range(_MAX_TRANSCRIPT_CHANGE_ATTEMPTS):
            transcript = self._latest_transcript(episode_id)
            with summary_generation_transaction(self.session, transcript.id):
                current_transcript = self._latest_transcript(episode_id)
                if current_transcript.id != transcript.id:
                    continue
                return self._generate_for_transcript(
                    episode,
                    transcript,
                    force=force,
                )
        raise ConflictError("The episode transcript changed during summary generation")
