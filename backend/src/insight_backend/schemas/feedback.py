from __future__ import annotations

from datetime import datetime
from typing import Literal, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..models.feedback import MessageFeedback


class FeedbackCreateRequest(BaseModel):
    conversation_id: int = Field(..., ge=1)
    message_id: int = Field(..., ge=1)
    value: Literal["up", "down"]


class FeedbackResponse(BaseModel):
    id: int
    conversation_id: int
    message_id: int
    value: Literal["up", "down"]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, feedback: "MessageFeedback") -> "FeedbackResponse":
        return cls(
            id=feedback.id,
            conversation_id=feedback.conversation_id,
            message_id=feedback.message_id,
            value=feedback.value,  # type: ignore[arg-type]
            created_at=feedback.created_at,
            updated_at=feedback.updated_at,
        )


class AdminFeedbackResponse(BaseModel):
    id: int
    value: Literal["up", "down"]
    created_at: datetime
    conversation_id: int
    conversation_title: str
    message_id: int
    message_content: str
    message_created_at: datetime
    owner_username: str
    author_username: str

    @classmethod
    def from_model(cls, feedback: "MessageFeedback") -> "AdminFeedbackResponse":
        msg = feedback.message
        conv = msg.conversation if msg else None
        owner_username = conv.user.username if conv and conv.user else ""
        return cls(
            id=feedback.id,
            value=feedback.value,  # type: ignore[arg-type]
            created_at=feedback.created_at,
            conversation_id=feedback.conversation_id,
            conversation_title=conv.title if conv else "",
            message_id=feedback.message_id,
            message_content=msg.content if msg else "",
            message_created_at=msg.created_at if msg else feedback.created_at,
            owner_username=owner_username,
            author_username=feedback.user.username if feedback.user else "",
        )
