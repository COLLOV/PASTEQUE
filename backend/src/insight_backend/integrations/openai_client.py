from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Optional, Sequence

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

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: Dict[str, Any],
        headers_extra: Dict[str, str] | None = None,
        stream: bool = False,
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if headers_extra:
            headers.update(headers_extra)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        log.debug("%s %s", method.upper(), url)
        try:
            if stream:
                response = self.client.stream(method.upper(), url, headers=headers, json=json_payload)
            else:
                response = self.client.request(method.upper(), url, headers=headers, json=json_payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            log.error("LLM backend unreachable at %s: %s", url, exc)
            raise OpenAIBackendError(
                f"Impossible de joindre le backend LLM ({self.base_url})."
                " Assurez-vous que vLLM est démarré ou que la configuration OPENAI_BASE_URL est correcte."
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            log.error("LLM backend returned %s for %s: %s", exc.response.status_code, url, body)
            raise OpenAIBackendError(
                f"Le backend LLM a retourné un statut {exc.response.status_code}."
                " Consultez ses logs pour plus de détails."
            ) from exc
        except httpx.HTTPError as exc:
            log.error("LLM backend request failed for %s: %s", url, exc)
            raise OpenAIBackendError("Erreur lors de l'appel au backend LLM.") from exc
        return response

    def chat_completions(self, *, model: str, messages: List[Dict[str, str]], **params: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": model, "messages": messages}
        payload.update(params)
        resp = self._request("post", "/chat/completions", json_payload=payload)
        return resp.json()

    def stream_chat_completions(
        self, *, model: str, messages: List[Dict[str, str]], **params: Any
    ) -> Iterator[Dict[str, Any]]:
        """Stream OpenAI-compatible chat completions as raw SSE JSON chunks.

        Yields parsed JSON dicts from lines starting with ``data: ``. Stops on ``[DONE]``.
        """
        headers_extra = {"Accept": "text/event-stream"}
        payload: Dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        payload.update(params)
        response = self._request(
            "post",
            "/chat/completions",
            json_payload=payload,
            headers_extra=headers_extra,
            stream=True,
        )
        try:
            with response as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: ") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        yield json.loads(data)
                    except Exception as exc:  # pragma: no cover - defensive parsing
                        log.error("Invalid SSE chunk: %s", exc)
                        continue
        finally:
            response.close()

    def embeddings(self, *, model: str, inputs: Sequence[str]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"model": model, "input": list(inputs)}
        resp = self._request("post", "/embeddings", json_payload=payload)
        return resp.json()
