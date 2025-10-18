from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    metadata: Dict[str, Any] | None = None


class ChatResponse(BaseModel):
    reply: str
    metadata: Dict[str, Any] | None = None

