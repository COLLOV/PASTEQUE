from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # import for type checking / linting only
    from .user import User
    from .feedback import MessageFeedback

from ..core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # JSON settings per conversation (e.g., NL→SQL preferences like excluded tables)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="conversations")
    messages: Mapped[list["ConversationMessage"]] = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )
    events: Mapped[list["ConversationEvent"]] = relationship(
        "ConversationEvent",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationEvent.created_at",
    )
    feedback: Mapped[list["MessageFeedback"]] = relationship(
        "MessageFeedback",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageFeedback.created_at",
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")
    feedback: Mapped[list["MessageFeedback"]] = relationship(
        "MessageFeedback",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageFeedback.created_at",
    )


class ConversationEvent(Base):
    __tablename__ = "conversation_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="events")
