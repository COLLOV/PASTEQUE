from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional

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

    def stream_chat_completions(
        self, *, model: str, messages: List[Dict[str, str]], **params: Any
    ) -> Iterator[Dict[str, Any]]:
        """Stream OpenAI-compatible chat completions as raw SSE JSON chunks.

        Yields parsed JSON dicts from lines starting with ``data: ``. Stops on ``[DONE]``.
        """
        url = f"{self.base_url}/chat/completions"
        headers: Dict[str, str] = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: Dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        payload.update(params)
        log.debug("STREAM %s model=%s", url, model)
        try:
            with self.client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    # Expect SSE lines like: "data: {json}" or "data: [DONE]"
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        yield resp.json_loader(data)
                    except Exception as exc:  # pragma: no cover - defensive parsing
                        log.error("Invalid SSE chunk: %s", exc)
                        continue
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
