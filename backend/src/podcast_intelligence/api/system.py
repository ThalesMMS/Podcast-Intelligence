from __future__ import annotations

import uuid

from fastapi import APIRouter

from podcast_intelligence.dependencies import AuthDep, RegistryDep, SessionDep, SettingsDep
from podcast_intelligence.schemas import (
    ProviderCapabilitiesResponse,
    SearchRequest,
    SearchResult,
)
from podcast_intelligence.services.retrieval import RetrievalService

router = APIRouter(tags=["system"])


@router.get("/providers", response_model=ProviderCapabilitiesResponse)
def provider_capabilities(registry: RegistryDep) -> ProviderCapabilitiesResponse:
    return ProviderCapabilitiesResponse(providers=registry.capabilities())


@router.post("/search", response_model=list[SearchResult])
def search(
    request: SearchRequest,
    auth: AuthDep,
    session: SessionDep,
    settings: SettingsDep,
    registry: RegistryDep,
) -> list[SearchResult]:
    results = RetrievalService(session, settings, registry.embeddings).search(
        auth.workspace_id,
        request.query,
        episode_id=request.episode_id,
        limit=request.limit,
    )
    return [
        SearchResult(
            chunk_id=uuid.UUID(result.chunk_id),
            episode_id=uuid.UUID(result.episode_id),
            episode_title=result.episode_title,
            text=result.text,
            start_ms=result.start_ms,
            end_ms=result.end_ms,
            speaker_labels=result.speaker_labels,
            score=result.combined_score,
        )
        for result in results
    ]
