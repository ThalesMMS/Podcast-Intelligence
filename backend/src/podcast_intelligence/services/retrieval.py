from __future__ import annotations

import math
import re
import uuid
from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from podcast_intelligence.config import Settings
from podcast_intelligence.domain.ports import EmbeddingProvider
from podcast_intelligence.domain.types import RetrievedChunk
from podcast_intelligence.enums import TranscriptStatus
from podcast_intelligence.models import Episode, KnowledgeChunk, Transcript

_TOKEN_RE = re.compile(r"[\wÀ-ÖØ-öø-ÿ]+", re.UNICODE)
_LOCAL_CANDIDATE_LIMIT = 10_000


class _ScoredChunk(TypedDict):
    chunk: KnowledgeChunk
    episode: Episode
    vector: float
    lexical: float


def _vector_similarity(distance: float | None) -> float:
    resolved_distance = 1.0 if distance is None else float(distance)
    return max(0.0, 1.0 - resolved_distance)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _lexical_similarity(query: str, text: str) -> float:
    """Small, deterministic desktop fallback for PostgreSQL full-text ranking.

    The server deployment keeps PostgreSQL's language-independent `simple`
    configuration. Desktop mode uses normalized token coverage plus an exact
    phrase bonus. It intentionally avoids platform-specific SQLite extensions
    so packaged builds behave the same on Windows and macOS.
    """

    normalized_query = " ".join(query.casefold().split())
    normalized_text = " ".join(text.casefold().split())
    query_tokens = _TOKEN_RE.findall(normalized_query)
    if not query_tokens:
        return 0.0
    text_tokens = set(_TOKEN_RE.findall(normalized_text))
    matched = sum(1 for token in query_tokens if token in text_tokens)
    coverage = matched / len(query_tokens)
    phrase_bonus = 0.2 if normalized_query and normalized_query in normalized_text else 0.0
    return min(1.0, coverage * 0.8 + phrase_bonus)


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

    def _materialize_results(
        self,
        records: dict[uuid.UUID, _ScoredChunk],
        *,
        limit: int,
    ) -> list[RetrievedChunk]:
        results: list[RetrievedChunk] = []
        for record in records.values():
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

    def _search_local(
        self,
        base: Select[tuple[KnowledgeChunk, Episode]],
        query_text: str,
        vector: Sequence[float],
        *,
        limit: int,
    ) -> list[RetrievedChunk]:
        rows = self.session.execute(base.limit(_LOCAL_CANDIDATE_LIMIT)).all()
        records: dict[uuid.UUID, _ScoredChunk] = {}
        for chunk, episode in rows:
            vector_score = 0.0
            if chunk.embedding is not None and chunk.embedding_model == self.embeddings.model_name:
                vector_score = _cosine_similarity(chunk.embedding, vector)
            lexical_score = _lexical_similarity(query_text, chunk.text)
            if vector_score <= 0.0 and lexical_score <= 0.0:
                continue
            records[chunk.id] = {
                "chunk": chunk,
                "episode": episode,
                "vector": vector_score,
                "lexical": lexical_score,
            }
        return self._materialize_results(records, limit=limit)

    def _search_postgresql(
        self,
        base: Select[tuple[KnowledgeChunk, Episode]],
        query_text: str,
        vector: Sequence[float],
        *,
        limit: int,
    ) -> list[RetrievedChunk]:
        candidate_limit = min(max(limit * 4, 20), 200)
        vector_distance = KnowledgeChunk.embedding.cosine_distance(list(vector))
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

        records: dict[uuid.UUID, _ScoredChunk] = {}
        for chunk, episode, distance in vector_rows:
            records[chunk.id] = {
                "chunk": chunk,
                "episode": episode,
                "vector": _vector_similarity(distance),
                "lexical": 0.0,
            }
        max_lexical = max((float(row.rank or 0.0) for row in lexical_rows), default=1.0)
        for chunk, episode, rank in lexical_rows:
            record = records.setdefault(
                chunk.id,
                {"chunk": chunk, "episode": episode, "vector": 0.0, "lexical": 0.0},
            )
            record["lexical"] = float(rank or 0.0) / max(max_lexical, 1e-9)
        return self._materialize_results(records, limit=limit)

    def search(
        self,
        workspace_id: uuid.UUID,
        query_text: str,
        *,
        episode_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> list[RetrievedChunk]:
        resolved_limit = limit or self.settings.retrieval_top_k
        vector = self.embeddings.embed([query_text])[0]
        base = self._base_query(workspace_id, episode_id)
        if self.session.get_bind().dialect.name == "postgresql":
            return self._search_postgresql(
                base,
                query_text,
                vector,
                limit=resolved_limit,
            )
        return self._search_local(base, query_text, vector, limit=resolved_limit)
