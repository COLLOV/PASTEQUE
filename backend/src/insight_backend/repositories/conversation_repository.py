from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session, joinedload

from ..models.conversation import Conversation, ConversationMessage, ConversationEvent


log = logging.getLogger("insight.repositories.conversation")


class ConversationRepository:
    def __init__(self, session: Session):
        self.session = session

    # Conversations
    def create(self, *, user_id: int, title: str) -> Conversation:
        conv = Conversation(user_id=user_id, title=title)
        self.session.add(conv)
        log.info("Conversation created (user_id=%s, title=%s)", user_id, title)
        return conv

    def list_by_user(self, user_id: int) -> list[Conversation]:
        items = (
            self.session.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .all()
        )
        log.info("Retrieved %d conversations for user_id=%s", len(items), user_id)
        return items

    def get_by_id_for_user(self, conversation_id: int, user_id: int) -> Conversation | None:
        return (
            self.session.query(Conversation)
            .options(joinedload(Conversation.messages), joinedload(Conversation.events))
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .one_or_none()
        )

    # Messages
    def append_message(self, *, conversation_id: int, role: str, content: str) -> ConversationMessage:
        msg = ConversationMessage(conversation_id=conversation_id, role=role, content=content)
        self.session.add(msg)
        # touch conversation updated_at
        self.session.query(Conversation).filter(Conversation.id == conversation_id).update({})
        log.info(
            "Appended message (conversation_id=%s, role=%s, preview=%s)",
            conversation_id,
            role,
            (content[:60] + "…") if len(content) > 60 else content,
        )
        return msg

    # Events (sql | rows | plan | meta | done)
    def add_event(self, *, conversation_id: int, kind: str, payload: dict[str, Any] | None) -> ConversationEvent:
        evt = ConversationEvent(conversation_id=conversation_id, kind=kind, payload=payload)
        self.session.add(evt)
        # touch conversation updated_at
        self.session.query(Conversation).filter(Conversation.id == conversation_id).update({})
        log.debug("Added event (conversation_id=%s, kind=%s)", conversation_id, kind)
        return evt

