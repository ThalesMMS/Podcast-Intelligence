from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from podcast_intelligence.domain.errors import NotFoundError
from podcast_intelligence.domain.ports import LanguageModel
from podcast_intelligence.enums import MessageRole
from podcast_intelligence.models import (
    Conversation,
    Episode,
    Message,
    Transcript,
    TranscriptSegment,
)
from podcast_intelligence.schemas import ChatResponse, CitationResponse
from podcast_intelligence.services.retrieval import RetrievalService


class ChatService:
    def __init__(
        self,
        session: Session,
        retrieval: RetrievalService,
        llm: LanguageModel,
    ) -> None:
        self.session = session
        self.retrieval = retrieval
        self.llm = llm

    def create_conversation(
        self,
        workspace_id: uuid.UUID,
        episode_id: uuid.UUID,
        title: str | None = None,
    ) -> Conversation:
        episode = self.session.scalar(
            select(Episode).where(
                Episode.id == episode_id,
                Episode.workspace_id == workspace_id,
            )
        )
        if episode is None:
            raise NotFoundError("Episode not found")
        conversation = Conversation(
            workspace_id=workspace_id,
            episode_id=episode_id,
            title=title or episode.title,
        )
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def _conversation(self, workspace_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
        conversation = self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.workspace_id == workspace_id,
            )
        )
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    def ask(
        self,
        workspace_id: uuid.UUID,
        conversation_id: uuid.UUID,
        question: str,
    ) -> ChatResponse:
        conversation = self._conversation(workspace_id, conversation_id)
        history_messages = list(
            self.session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(12)
            )
        )
        history: Sequence[dict[str, str]] = [
            {"role": message.role.value, "content": message.content}
            for message in reversed(history_messages)
        ]

        user_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=question,
        )
        self.session.add(user_message)
        self.session.flush()

        contexts = self.retrieval.search(
            workspace_id,
            question,
            episode_id=conversation.episode_id,
        )
        answer = self.llm.answer(question, contexts, history)
        allowed_ids = {segment_id for context in contexts for segment_id in context.segment_ids}
        cited_ids = list(
            dict.fromkeys(
                segment_id for segment_id in answer.cited_segment_ids if segment_id in allowed_ids
            )
        )
        if not cited_ids and contexts and not answer.insufficient_evidence:
            cited_ids = contexts[0].segment_ids[:3]

        valid_uuids: list[uuid.UUID] = []
        for segment_id in cited_ids:
            try:
                valid_uuids.append(uuid.UUID(segment_id))
            except ValueError:
                continue
        segments = list(
            self.session.scalars(
                select(TranscriptSegment)
                .join(Transcript, Transcript.id == TranscriptSegment.transcript_id)
                .where(
                    TranscriptSegment.id.in_(valid_uuids),
                    Transcript.episode_id == conversation.episode_id,
                )
                .order_by(TranscriptSegment.start_ms)
            )
        )
        by_id = {str(segment.id): segment for segment in segments}
        citations: list[CitationResponse] = []
        for segment_id in cited_ids:
            segment = by_id.get(segment_id)
            if segment is None:
                continue
            speaker = None
            if segment.speaker:
                speaker = segment.speaker.display_name or segment.speaker.label
            citations.append(
                CitationResponse(
                    segment_id=segment.id,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    speaker=speaker,
                    quote=segment.text,
                )
            )

        assistant_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=answer.answer,
            citations_json=[citation.model_dump(mode="json") for citation in citations],
            retrieval_json={"chunks": [context.model_dump(mode="json") for context in contexts]},
            provider=self.llm.provider_name,
            model=self.llm.model_name,
        )
        self.session.add(assistant_message)
        self.session.commit()
        self.session.refresh(assistant_message)
        return ChatResponse(
            message_id=assistant_message.id,
            answer=answer.answer,
            citations=citations,
            insufficient_evidence=answer.insufficient_evidence,
        )
