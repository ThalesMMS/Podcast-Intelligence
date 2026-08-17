from __future__ import annotations

import uuid
from typing import TypedDict

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from podcast_intelligence.config import Settings
from podcast_intelligence.domain.ports import EmbeddingProvider
from podcast_intelligence.domain.types import RetrievedChunk
from podcast_intelligence.enums import TranscriptStatus
from podcast_intelligence.models import Episode, KnowledgeChunk, Transcript


class _ScoredChunk(TypedDict):
    chunk: KnowledgeChunk
    episode: Episode
    vector: float
    lexical: float


def _vector_similarity(distance: float | None) -> float:
    resolved_distance = 1.0 if distance is None else float(distance)
    return max(0.0, 1.0 - resolved_distance)


class RetrievalService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        embeddings: EmbeddingProvider,
    ) -> None:
        self.session = session
        self.settings = settings
        self.embeddings = embeddings

    def _base_query(
        self, workspace_id: uuid.UUID, episode_id: uuid.UUID | None
    ) -> Select[tuple[KnowledgeChunk, Episode]]:
        latest_transcript_id = (
            select(Transcript.id)
            .where(
                Transcript.episode_id == KnowledgeChunk.episode_id,
                Transcript.status == TranscriptStatus.READY,
            )
            .order_by(Transcript.version.desc())
            .limit(1)
            .correlate(KnowledgeChunk)
            .scalar_subquery()
        )
        query = (
            select(KnowledgeChunk, Episode)
            .join(Episode, Episode.id == KnowledgeChunk.episode_id)
            .where(
                KnowledgeChunk.workspace_id == workspace_id,
                KnowledgeChunk.transcript_id == latest_transcript_id,
            )
        )
        if episode_id:
            query = query.where(KnowledgeChunk.episode_id == episode_id)
        return query

    def search(
        self,
        workspace_id: uuid.UUID,
        query_text: str,
        *,
        episode_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[RetrievedChunk]:
        limit = limit or self.settings.retrieval_top_k
        candidate_limit = min(max(limit * 4, 20), 200)
        vector = self.embeddings.embed([query_text])[0]

        base = self._base_query(workspace_id, episode_id)
        vector_distance = KnowledgeChunk.embedding.cosine_distance(vector)
        vector_rows = self.session.execute(
            base.where(
                KnowledgeChunk.embedding.is_not(None),
                KnowledgeChunk.embedding_model == self.embeddings.model_name,
            )
            .add_columns(vector_distance.label("distance"))
            .order_by(vector_distance)
            .limit(candidate_limit)
        ).all()

        search_config: ColumnElement[str] = literal_column("'simple'::regconfig")
        lexical_vector = func.to_tsvector(search_config, KnowledgeChunk.text)
        lexical_query = func.websearch_to_tsquery(search_config, query_text)
        lexical_rank = func.ts_rank_cd(lexical_vector, lexical_query)
        lexical_rows = self.session.execute(
            base.add_columns(lexical_rank.label("rank"))
            .where(lexical_vector.bool_op("@@")(lexical_query))
            .order_by(lexical_rank.desc())
            .limit(candidate_limit)
        ).all()

        merged: dict[uuid.UUID, _ScoredChunk] = {}
        for chunk, episode, distance in vector_rows:
            merged[chunk.id] = {
                "chunk": chunk,
                "episode": episode,
                "vector": _vector_similarity(distance),
                "lexical": 0.0,
            }
        max_lexical = max((float(row.rank or 0.0) for row in lexical_rows), default=1.0)
        for chunk, episode, rank in lexical_rows:
            record = merged.setdefault(
                chunk.id,
                {"chunk": chunk, "episode": episode, "vector": 0.0, "lexical": 0.0},
            )
            record["lexical"] = float(rank or 0.0) / max(max_lexical, 1e-9)

        results: list[RetrievedChunk] = []
        for record in merged.values():
            chunk = record["chunk"]
            episode = record["episode"]
            vector_score = record["vector"]
            lexical_score = record["lexical"]
            combined = (
                vector_score * self.settings.retrieval_vector_weight
                + lexical_score * self.settings.retrieval_lexical_weight
            )
            results.append(
                RetrievedChunk(
                    chunk_id=str(chunk.id),
                    episode_id=str(chunk.episode_id),
                    episode_title=episode.title,
                    text=chunk.text,
                    start_ms=chunk.start_ms,
                    end_ms=chunk.end_ms,
                    segment_ids=list(chunk.segment_ids),
                    speaker_labels=list(chunk.speaker_labels),
                    lexical_score=lexical_score,
                    vector_score=vector_score,
                    combined_score=combined,
                )
            )
        return sorted(results, key=lambda item: item.combined_score, reverse=True)[:limit]
