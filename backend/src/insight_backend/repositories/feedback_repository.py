from __future__ import annotations

import logging

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..models.feedback import MessageFeedback
from ..models.conversation import ConversationMessage, Conversation

log = logging.getLogger("insight.repositories.feedback")


class FeedbackRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, feedback_id: int) -> MessageFeedback | None:
        return (
            self.session.query(MessageFeedback)
            .options(
                joinedload(MessageFeedback.user),
                joinedload(MessageFeedback.message)
                .joinedload(ConversationMessage.conversation)
                .joinedload(Conversation.user),
            )
            .filter(MessageFeedback.id == feedback_id)
            .one_or_none()
        )

    def upsert(
        self,
        *,
        user_id: int,
        conversation_id: int,
        message_id: int,
        value: str,
    ) -> MessageFeedback:
        normalized = (value or "").strip().lower()
        if normalized not in {"up", "down"}:
            raise ValueError("Invalid feedback value")
        existing = (
            self.session.query(MessageFeedback)
            .filter(
                MessageFeedback.user_id == user_id,
                MessageFeedback.message_id == message_id,
            )
            .one_or_none()
        )
        if existing:
            if existing.value != normalized:
                existing.value = normalized
                existing.updated_at = func.now()
            existing.is_archived = False
            log.info(
                "Feedback updated (id=%s, user_id=%s, conversation_id=%s, message_id=%s, value=%s)",
                existing.id,
                user_id,
                conversation_id,
                message_id,
                normalized,
            )
            return existing
        feedback = MessageFeedback(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            value=normalized,
            is_archived=False,
        )
        self.session.add(feedback)
        self.session.flush()
        log.info(
            "Feedback created (id=%s, user_id=%s, conversation_id=%s, message_id=%s, value=%s)",
            feedback.id,
            user_id,
            conversation_id,
            message_id,
            normalized,
        )
        return feedback

    def delete(self, feedback: MessageFeedback) -> None:
        self.session.delete(feedback)
        log.info(
            "Feedback deleted (id=%s, user_id=%s, message_id=%s)",
            feedback.id,
            feedback.user_id,
            feedback.message_id,
        )

    def list_for_conversation_user(
        self, *, conversation_id: int, user_id: int, include_archived: bool = False
    ) -> list[MessageFeedback]:
        query = (
            self.session.query(MessageFeedback)
            .filter(
                MessageFeedback.conversation_id == conversation_id,
                MessageFeedback.user_id == user_id,
            )
        )
        if not include_archived:
            query = query.filter(MessageFeedback.is_archived.is_(False))
        items = query.all()
        log.debug(
            "Loaded %d feedback items for conversation_id=%s user_id=%s include_archived=%s",
            len(items),
            conversation_id,
            user_id,
            include_archived,
        )
        return items

    def list_latest(self, *, limit: int = 200, archived: bool = False) -> list[MessageFeedback]:
        query = (
            self.session.query(MessageFeedback)
            .options(
                joinedload(MessageFeedback.user),
                joinedload(MessageFeedback.message)
                .joinedload(ConversationMessage.conversation)
                .joinedload(Conversation.user),
            )
            .filter(MessageFeedback.is_archived.is_(archived))
            .order_by(MessageFeedback.created_at.desc())
            .limit(limit)
        )
        items = query.all()
        log.debug("Loaded %d feedback items for admin (limit=%s archived=%s)", len(items), limit, archived)
        return items

    def archive(self, feedback: MessageFeedback) -> MessageFeedback:
        feedback.is_archived = True
        feedback.updated_at = func.now()
        log.info(
            "Feedback archived (id=%s, user_id=%s, message_id=%s)",
            feedback.id,
            feedback.user_id,
            feedback.message_id,
        )
        return feedback
