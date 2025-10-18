from __future__ import annotations

from typing import Any
import logging

from ..schemas.chat import ChatRequest, ChatResponse
from ..integrations.openai_client import OpenAICompatibleClient


log = logging.getLogger("insight.engines.openai")


class OpenAIChatEngine:
    """ChatEngine adossé à une API OpenAI-compatible (vLLM ou provider Z).

    Ce moteur reste volontairement minimal: pas de streaming, pas d'outils.
    """

    def __init__(self, *, client: OpenAICompatibleClient, model: str):
        self.client = client
        self.model = model

    def run(self, payload: ChatRequest) -> ChatResponse:  # type: ignore[valid-type]
        messages = [m.model_dump() for m in payload.messages]
        data: dict[str, Any] = self.client.chat_completions(model=self.model, messages=messages)
        # OpenAI-compatible: choices[0].message.content
        try:
            reply = data["choices"][0]["message"]["content"]
        except Exception as e:  # pragma: no cover - defensive; we want a clear error
            log.error("Invalid response from OpenAI-compatible backend: %s", e)
            raise
        return ChatResponse(reply=reply, metadata={"provider": "openai-compatible"})

