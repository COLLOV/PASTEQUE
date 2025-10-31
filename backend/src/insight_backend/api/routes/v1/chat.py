import json
import threading
import queue
import time
import uuid
from typing import Iterator
import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import StreamingResponse

from ....schemas.chat import ChatRequest, ChatResponse
from ....core.config import settings
from ....core.database import get_session, transactional
from ....core.security import get_current_user, user_is_admin
from ....models.user import User
from ....services.chat_service import ChatService
from ....services.router_service import RouterService
from ....engines.openai_engine import OpenAIChatEngine
from ....integrations.openai_client import OpenAICompatibleClient, OpenAIBackendError
from ....repositories.user_table_permission_repository import UserTablePermissionRepository
from ....repositories.conversation_repository import ConversationRepository
from ....repositories.user_repository import UserRepository
from ....utils.text import sanitize_title
from ....repositories.data_repository import DataRepository

log = logging.getLogger("insight.api.chat")

router = APIRouter(prefix="/chat")


def _normalize_exclude_tables(raw: list[object], *, max_items: int = 1000, max_len: int = 255) -> list[str]:
    """Validate and normalize a user-provided list of table names.

    - caps list length to ``max_items``
    - trims and truncates names to ``max_len``
    - deduplicates case-insensitively while preserving first-seen casing
    """
    out: list[str] = []
    seen: set[str] = set()
    count = 0
    for item in raw:
        if count >= max_items:
            break
        if not isinstance(item, str):
            continue
        cleaned = item.strip()[:max_len]
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        count += 1
    return out


def _apply_exclusions_and_defaults(
    *,
    session: Session,
    user_id: int,
    conversation_id: int,
    metadata: dict,
    allowed_tables: list[str] | None,
) -> list[str]:
    """Apply per-conversation exclusions and optionally save as user defaults.

    Returns the effective excluded tables that were persisted or hydrated.
    """
    repo = ConversationRepository(session)
    user_repo = UserRepository(session)

    excludes_in = metadata.get("exclude_tables") if isinstance(metadata, dict) else None
    save_default_flag = metadata.get("save_as_default") if isinstance(metadata, dict) else None
    save_as_default = bool(save_default_flag) if save_default_flag is not None else True  # keep current behavior

    if excludes_in is not None and isinstance(excludes_in, list):
        # Validate and filter against known tables
        normalized = _normalize_exclude_tables(excludes_in)
        available = set(DataRepository(tables_dir=settings.tables_dir).list_tables())
        allowed_lookup = {t.casefold() for t in (allowed_tables or list(available))}
        filtered = [t for t in normalized if t.casefold() in allowed_lookup and t in available]
        try:
            persisted = repo.set_excluded_tables(conversation_id=conversation_id, tables=filtered)
            if save_as_default:
                user_repo.set_default_excluded_tables(user_id=user_id, tables=persisted)
            return persisted
        except Exception:
            log.warning(
                "Failed to persist exclude_tables (conversation_id=%s, user_id=%s)",
                conversation_id,
                user_id,
                exc_info=True,
            )
            return []
    # Hydrate from existing conversation or user defaults
    try:
        saved = repo.get_excluded_tables(conversation_id=conversation_id)
        if not saved:
            saved = user_repo.get_default_excluded_tables(user_id=user_id)
        return saved or []
    except Exception:
        log.warning(
            "Failed to hydrate exclude_tables (conversation_id=%s, user_id=%s)",
            conversation_id,
            user_id,
            exc_info=True,
        )
        return []

@router.post("/completions", response_model=ChatResponse)
def chat_completion(  # type: ignore[valid-type]
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChatResponse:
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
    allowed_tables = None
    if not user_is_admin(current_user):
        allowed_tables = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)
    # Ensure conversation + persist user message atomically
    repo = ConversationRepository(session)
    meta = payload.metadata or {}
    with transactional(session):
        conv_id: int | None
        try:
            raw_id = meta.get("conversation_id") if isinstance(meta, dict) else None
            conv_id = int(raw_id) if raw_id is not None else None
        except Exception:
            conv_id = None
        conv = None
        if conv_id:
            conv = repo.get_by_id_for_user(conv_id, current_user.id)
        if conv is None:
            # Derive title from first user message
            title = "Nouvelle conversation"
            if payload.messages:
                for msg in payload.messages:
                    if msg.role == "user" and msg.content.strip():
                        title = sanitize_title(msg.content)
                        break
            conv = repo.create(user_id=current_user.id, title=title)
            session.flush()
            conv_id = conv.id
        # Merge/persist per-conversation exclusions (settings) with validation
        saved = _apply_exclusions_and_defaults(
            session=session,
            user_id=current_user.id,
            conversation_id=conv_id,
            metadata=payload.metadata or {},
            allowed_tables=allowed_tables,
        )
        if saved:
            payload.metadata = dict(payload.metadata or {})
            payload.metadata["exclude_tables"] = saved

        # Persist the last user message if any
        last = payload.messages[-1] if payload.messages else None
        if last and last.role == "user" and last.content:
            repo.append_message(conversation_id=conv_id, role="user", content=last.content)

    # First-message router gate (avoid useless SQL/NL2SQL work)
    if payload.messages and len(payload.messages) == 1:
        last = payload.messages[-1]
        if last.role == "user":
            decision = RouterService().decide(last.content)
            log.info(
                "Router decision: allow=%s route=%s conf=%.2f reason=%s",
                decision.allow,
                decision.route,
                decision.confidence,
                decision.reason,
            )
            if not decision.allow:
                text = "Ce n'est pas une question pour passer de la data à l'action"
                # Persist assistant reply
                try:
                    with transactional(session):
                        repo.append_message(conversation_id=conv_id, role="assistant", content=text)
                except SQLAlchemyError:
                    log.warning("Failed to persist router reply (conversation_id=%s)", conv_id, exc_info=True)
                return ChatResponse(reply=text, metadata={"provider": "router", "route": decision.route, "confidence": decision.confidence})

    try:
        resp = service.completion(payload, allowed_tables=allowed_tables)
        # Persist assistant reply
        if resp and isinstance(resp.reply, str):
            try:
                with transactional(session):
                    repo.append_message(conversation_id=conv_id, role="assistant", content=resp.reply)
            except SQLAlchemyError:
                log.exception("Failed to persist assistant reply (conversation_id=%s)", conv_id)
        # Return as-is (no conversation id field in schema), clients can fetch via separate API
        return resp
    except OpenAIBackendError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\n".encode("utf-8") + f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


@router.post("/stream")
def chat_stream(  # type: ignore[valid-type]
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
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
    allowed_tables = None
    if not user_is_admin(current_user):
        allowed_tables = UserTablePermissionRepository(session).get_allowed_tables(current_user.id)

    trace_id = f"chat-{uuid.uuid4().hex[:8]}"
    started = time.perf_counter()
    repo = ConversationRepository(session)

    # Resolve conversation id from metadata or create one on the fly
    conversation_id: int | None = None
    meta_in = payload.metadata or {}
    try:
        raw_id = meta_in.get("conversation_id") if isinstance(meta_in, dict) else None
        conversation_id = int(raw_id) if raw_id is not None else None
    except Exception:
        conversation_id = None
    with transactional(session):
        if conversation_id:
            existing = repo.get_by_id_for_user(conversation_id, current_user.id)
            if existing is None:
                conversation_id = None
        if not conversation_id:
            # Derive title from first user message
            title = "Nouvelle conversation"
            if payload.messages:
                for msg in payload.messages:
                    if msg.role == "user" and msg.content.strip():
                        title = sanitize_title(msg.content)
                        break
            conv = repo.create(user_id=current_user.id, title=title)
            session.flush()
            conversation_id = conv.id
        # Persist last user message immediately (if present)
        last = payload.messages[-1] if payload.messages else None
        if last and last.role == "user" and last.content:
            repo.append_message(conversation_id=conversation_id, role="user", content=last.content)
        # Merge/persist per-conversation exclusions (settings) with validation
        saved = _apply_exclusions_and_defaults(
            session=session,
            user_id=current_user.id,
            conversation_id=conversation_id,
            metadata=payload.metadata or {},
            allowed_tables=allowed_tables,
        )
        if saved:
            payload.metadata = dict(payload.metadata or {})
            payload.metadata["exclude_tables"] = saved

    def generate() -> Iterator[bytes]:
        seq = 0
        try:
            # Router gate on first message before any SQL activity
            last = payload.messages[-1] if payload.messages else None
            if payload.messages and len(payload.messages) == 1 and last and last.role == "user":
                decision = RouterService().decide(last.content)
                log.info(
                    "Router decision: allow=%s route=%s conf=%.2f reason=%s",
                    decision.allow,
                    decision.route,
                    decision.confidence,
                    decision.reason,
                )
                if not decision.allow:
                    prov = "router"
                    yield _sse("meta", {"request_id": trace_id, "provider": prov, "model": "rule", "conversation_id": conversation_id, "route": decision.route, "confidence": decision.confidence})
                    text = "Ce n'est pas une question pour passer de la data à l'action"
                    for line in text.splitlines(True):
                        if not line:
                            continue
                        seq += 1
                        yield _sse("delta", {"seq": seq, "content": line})
                    elapsed = max(time.perf_counter() - started, 1e-6)
                    try:
                        with transactional(session):
                            repo.append_message(conversation_id=conversation_id, role="assistant", content=text)
                    except SQLAlchemyError:
                        log.warning("Failed to persist router reply (conversation_id=%s)", conversation_id, exc_info=True)
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

            # 1) MindsDB passthrough (/sql ...) or NL→SQL mode
            if last and last.role == "user" and last.content.strip().casefold().startswith("/sql "):
                prov = "mindsdb-sql"
                yield _sse("meta", {"request_id": trace_id, "provider": prov, "model": model, "conversation_id": conversation_id})
                q: "queue.Queue[tuple[str, dict] | tuple[str, object]]" = queue.Queue()

                def emit(evt: str, data: dict) -> None:
                    # Push to SSE queue only; persist on the consumer thread to avoid cross-thread session use
                    q.put((evt, data))

                result_holder: dict[str, object] = {}

                def worker() -> None:
                    resp = service.completion(payload, events=emit, allowed_tables=allowed_tables)
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
                    # Persist events on the request thread (session is not thread-safe)
                    try:
                        if not (kind == "rows" and not (isinstance(data, dict) and data.get("purpose") == "evidence")):
                            with transactional(session):
                                repo.add_event(conversation_id=conversation_id, kind=kind, payload=data)
                    except SQLAlchemyError:
                        log.warning("Failed to persist event kind=%s for conversation_id=%s", kind, conversation_id, exc_info=True)
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
                # Persist assistant final message
                try:
                    with transactional(session):
                        repo.append_message(conversation_id=conversation_id, role="assistant", content=text)
                except SQLAlchemyError:
                    log.warning("Failed to persist assistant message (conversation_id=%s)", conversation_id, exc_info=True)

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

            # Per-request override: if payload.metadata.nl2sql is explicitly set, use it;
            # otherwise fall back to settings.nl2sql_enabled.
            meta = payload.metadata or {}
            nl2sql_flag = meta.get("nl2sql") if isinstance(meta, dict) else None
            nl2sql_enabled = bool(nl2sql_flag) if (nl2sql_flag is not None) else settings.nl2sql_enabled

            if nl2sql_enabled and last and last.role == "user":
                prov = "nl2sql"
                yield _sse("meta", {"request_id": trace_id, "provider": prov, "model": model, "conversation_id": conversation_id})
                q: "queue.Queue[tuple[str, dict] | tuple[str, object]]" = queue.Queue()

                def emit(evt: str, data: dict) -> None:
                    # Queue only; persistence happens on consumer side in this request thread
                    q.put((evt, data))

                result_holder: dict[str, object] = {}

                def worker() -> None:
                    resp = service.completion(payload, events=emit, allowed_tables=allowed_tables)
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
                    try:
                        if not (kind == "rows" and not (isinstance(data, dict) and data.get("purpose") == "evidence")):
                            with transactional(session):
                                repo.add_event(conversation_id=conversation_id, kind=kind, payload=data)
                    except SQLAlchemyError:
                        log.warning("Failed to persist event kind=%s for conversation_id=%s", kind, conversation_id, exc_info=True)
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
                try:
                    with transactional(session):
                        repo.append_message(conversation_id=conversation_id, role="assistant", content=text)
                except SQLAlchemyError:
                    log.warning("Failed to persist assistant message (conversation_id=%s)", conversation_id, exc_info=True)

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
            yield _sse("meta", {"request_id": trace_id, "provider": provider, "model": model, "conversation_id": conversation_id})
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
            try:
                with transactional(session):
                    repo.append_message(conversation_id=conversation_id, role="assistant", content=content_full)
            except SQLAlchemyError:
                log.warning("Failed to persist assistant message (conversation_id=%s)", conversation_id, exc_info=True)
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
