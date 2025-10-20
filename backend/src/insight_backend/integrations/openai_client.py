from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx


class OpenAIBackendError(RuntimeError):
    """Raised when the OpenAI-compatible backend cannot satisfy a request."""
    pass


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
        try:
            resp = self.client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            log.error("LLM backend unreachable at %s: %s", url, exc)
            raise OpenAIBackendError(
                f"Impossible de joindre le backend LLM ({self.base_url})."
                " Assurez-vous que vLLM est démarré ou que la configuration OPENAI_BASE_URL est correcte."
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            log.error(
                "LLM backend returned %s for %s: %s", exc.response.status_code, url, body
            )
            raise OpenAIBackendError(
                f"Le backend LLM a retourné un statut {exc.response.status_code}."
                " Consultez ses logs pour plus de détails."
            ) from exc
        except httpx.HTTPError as exc:
            log.error("LLM backend request failed for %s: %s", url, exc)
            raise OpenAIBackendError("Erreur lors de l'appel au backend LLM.") from exc
        return resp.json()
