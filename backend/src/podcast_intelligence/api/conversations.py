from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from podcast_intelligence.dependencies import AuthDep, RegistryDep, SessionDep, SettingsDep
from podcast_intelligence.domain.errors import NotFoundError
from podcast_intelligence.models import Conversation, Message
from podcast_intelligence.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationResponse,
)
from podcast_intelligence.services.chat import ChatService
from podcast_intelligence.services.retrieval import RetrievalService

router = APIRouter(tags=["conversations"])


def _service(session: SessionDep, settings: SettingsDep, registry: RegistryDep) -> ChatService:
    retrieval = RetrievalService(session, settings, registry.embeddings)
    return ChatService(session, retrieval, registry.llm)


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    request: ConversationCreateRequest,
    auth: AuthDep,
    session: SessionDep,
    settings: SettingsDep,
    registry: RegistryDep,
) -> Conversation:
    return _service(session, settings, registry).create_conversation(
        auth.workspace_id, request.episode_id, request.title
    )


@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
def ask_conversation(
    conversation_id: uuid.UUID,
    request: ChatRequest,
    auth: AuthDep,
    session: SessionDep,
    settings: SettingsDep,
    registry: RegistryDep,
) -> ChatResponse:
    return _service(session, settings, registry).ask(
        auth.workspace_id, conversation_id, request.question
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: uuid.UUID,
    auth: AuthDep,
    session: SessionDep,
) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == auth.workspace_id,
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: uuid.UUID,
    auth: AuthDep,
    session: SessionDep,
) -> list[dict[str, object]]:
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == auth.workspace_id,
        )
    )
    if conversation is None:
        raise NotFoundError("Conversation not found")
    messages = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    )
    return [
        {
            "id": str(message.id),
            "role": message.role.value,
            "content": message.content,
            "citations": message.citations_json,
            "created_at": message.created_at,
        }
        for message in messages
    ]
