from fastapi import APIRouter

from podcast_intelligence.api.conversations import router as conversations_router
from podcast_intelligence.api.episodes import router as episodes_router
from podcast_intelligence.api.imports import router as imports_router
from podcast_intelligence.api.system import router as system_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(imports_router)
api_router.include_router(episodes_router)
api_router.include_router(conversations_router)
api_router.include_router(system_router)
