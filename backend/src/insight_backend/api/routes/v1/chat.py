import time
import uuid
from typing import Iterator

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse
import json
import threading
import queue
from ....schemas.chat import ChatRequest, ChatResponse
from ....core.config import settings
from ....services.chat_service import ChatService
from ....engines.openai_engine import OpenAIChatEngine
from ....integrations.openai_client import OpenAICompatibleClient, OpenAIBackendError

router = APIRouter(prefix="/chat")


@router.post("/completions", response_model=ChatResponse)
def chat_completion(payload: ChatRequest) -> ChatResponse:  # type: ignore[valid-type]
    """Chat completions via moteur OpenAI‑compatible.

    - En mode local (`LLM_MODE=local`): utilise `VLLM_BASE_URL` + `Z_LOCAL_MODEL`.
    - En mode API (`LLM_MODE=api`): utilise `OPENAI_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`.
    """
    if settings.llm_mode not in {"local", "api"}:
        raise HTTPException(status_code=500, detail="Invalid LLM_MODE; expected 'local' or 'api'")

    if settings.llm_mode == "local":
        base_url = settings.vllm_base_url
        model = settings.z_local_model
        api_key = None
    else:
        base_url = settings.openai_base_url
        model = settings.llm_model
        api_key = settings.openai_api_key

    if not base_url or not model:
        raise HTTPException(status_code=500, detail="LLM base_url/model not configured")

    client = OpenAICompatibleClient(base_url=base_url, api_key=api_key)
    engine = OpenAIChatEngine(client=client, model=model)
    service = ChatService(engine)
    try:
        return service.completion(payload)
    except OpenAIBackendError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\n".encode("utf-8") + f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


@router.post("/stream")
def chat_stream(payload: ChatRequest):  # type: ignore[valid-type]
    """SSE streaming for chat completions.

    Emits events: meta → delta* → done, or error on failure.
    """
    if settings.llm_mode not in {"local", "api"}:
        raise HTTPException(status_code=500, detail="Invalid LLM_MODE; expected 'local' or 'api'")

    if settings.llm_mode == "local":
        base_url = settings.vllm_base_url
        model = settings.z_local_model
        api_key = None
        provider = "vllm-local"
    else:
        base_url = settings.openai_base_url
        model = settings.llm_model
        api_key = settings.openai_api_key
        provider = "openai-api"

    if not base_url or not model:
        raise HTTPException(status_code=500, detail="LLM base_url/model not configured")

    client = OpenAICompatibleClient(base_url=base_url, api_key=api_key)
    engine = OpenAIChatEngine(client=client, model=model)
    service = ChatService(engine)

    trace_id = f"chat-{uuid.uuid4().hex[:8]}"
    started = time.perf_counter()

    def generate() -> Iterator[bytes]:
        seq = 0
        try:
            # 1) MindsDB passthrough (/sql ...) or NL→SQL mode
            last = payload.messages[-1] if payload.messages else None
            if last and last.role == "user" and last.content.strip().casefold().startswith("/sql "):
                prov = "mindsdb-sql"
                yield _sse("meta", {"request_id": trace_id, "provider": prov, "model": model})
                q: "queue.Queue[tuple[str, dict] | tuple[str, object]]" = queue.Queue()

                def emit(evt: str, data: dict) -> None:
                    q.put((evt, data))

                result_holder: dict[str, object] = {}

                def worker() -> None:
                    resp = service.completion(payload, events=emit)
                    result_holder["resp"] = resp
                    q.put(("__final__", resp))

                th = threading.Thread(target=worker, daemon=True)
                th.start()
                while True:
                    item = q.get()
                    if not isinstance(item, tuple) or len(item) != 2:
                        continue
                    kind, data = item
                    if kind == "__final__":
                        break
                    yield _sse(kind, data)  # 'sql' | 'rows' | 'plan' | etc.
                resp = result_holder.get("resp")
                if isinstance(resp, ChatResponse):
                    text = resp.reply or ""
                else:
                    text = ""
                for line in text.splitlines(True):
                    if not line:
                        continue
                    seq += 1
                    yield _sse("delta", {"seq": seq, "content": line})
                elapsed = max(time.perf_counter() - started, 1e-6)
                yield _sse(
                    "done",
                    {
                        "id": trace_id,
                        "content_full": text,
                        "usage": None,
                        "finish_reason": "stop",
                        "elapsed_s": round(elapsed, 3),
                    },
                )
                return

            if settings.nl2sql_enabled and last and last.role == "user":
                prov = "nl2sql"
                yield _sse("meta", {"request_id": trace_id, "provider": prov, "model": model})
                q: "queue.Queue[tuple[str, dict] | tuple[str, object]]" = queue.Queue()

                def emit(evt: str, data: dict) -> None:
                    q.put((evt, data))

                result_holder: dict[str, object] = {}

                def worker() -> None:
                    resp = service.completion(payload, events=emit)
                    result_holder["resp"] = resp
                    q.put(("__final__", resp))

                th = threading.Thread(target=worker, daemon=True)
                th.start()
                while True:
                    item = q.get()
                    if not isinstance(item, tuple) or len(item) != 2:
                        continue
                    kind, data = item
                    if kind == "__final__":
                        break
                    yield _sse(kind, data)  # 'plan' | 'sql' | 'rows'
                resp = result_holder.get("resp")
                if isinstance(resp, ChatResponse):
                    text = resp.reply or ""
                else:
                    text = ""
                for line in text.splitlines(True):
                    if not line:
                        continue
                    seq += 1
                    yield _sse("delta", {"seq": seq, "content": line})
                elapsed = max(time.perf_counter() - started, 1e-6)
                yield _sse(
                    "done",
                    {
                        "id": trace_id,
                        "content_full": text,
                        "usage": None,
                        "finish_reason": "stop",
                        "elapsed_s": round(elapsed, 3),
                    },
                )
                return

            # 2) Default LLM streaming
            # Default LLM streaming branch
            yield _sse("meta", {"request_id": trace_id, "provider": provider, "model": model})
            full: list[str] = []
            for event in engine.stream(payload):
                if event.get("type") == "delta":
                    text = event.get("content") or ""
                    if not text:
                        continue
                    seq += 1
                    full.append(text)
                    yield _sse("delta", {"seq": seq, "content": text})
                elif event.get("type") == "finish":
                    # ignore here; finalization below
                    pass
            content_full = "".join(full)
            elapsed = max(time.perf_counter() - started, 1e-6)
            # Logging via ChatService for consistency
            service._log_completion(  # noqa: SLF001 — intentional internal reuse for logging
                ChatResponse(reply=content_full, metadata={"provider": provider}),
                context="stream done (engine)",
            )
            yield _sse(
                "done",
                {
                    "id": trace_id,
                    "content_full": content_full,
                    "usage": None,
                    "finish_reason": "stop",
                    "elapsed_s": round(elapsed, 3),
                },
            )
        except OpenAIBackendError as exc:
            yield _sse("error", {"code": "backend_error", "message": str(exc)})
        except Exception as exc:  # pragma: no cover - unexpected
            yield _sse("error", {"code": "internal_error", "message": str(exc)})

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(generate(), media_type="text/event-stream", headers=headers)
