from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx


log = logging.getLogger("insight.integrations.openai")


class OpenAICompatibleClient:
    """Minimal OpenAI-compatible client for chat completions.

    Works with vLLM's OpenAI server and providers that expose the same schema.
    Only implements what we need now to keep the surface small.
    """

    def __init__(self, *, base_url: str, api_key: Optional[str] = None, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(timeout=timeout_s)

    def chat_completions(self, *, model: str, messages: List[Dict[str, str]], **params: Any) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: Dict[str, Any] = {"model": model, "messages": messages}
        payload.update(params)
        log.debug("POST %s model=%s", url, model)
        resp = self.client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()

