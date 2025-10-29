from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ....core.database import get_session
from ....models.user import User
from ....repositories.conversation_repository import ConversationRepository
from ....core.security import get_current_user


router = APIRouter(prefix="/conversations")


@router.get("")
def list_conversations(  # type: ignore[valid-type]
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    repo = ConversationRepository(session)
    items = repo.list_by_user(current_user.id)
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in items
    ]


@router.post("")
def create_conversation(  # type: ignore[valid-type]
    payload: dict[str, Any] | None = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    title = (payload or {}).get("title") or "Nouvelle conversation"
    repo = ConversationRepository(session)
    conv = repo.create(user_id=current_user.id, title=title)
    session.commit()
    return {"id": conv.id, "title": conv.title}


@router.get("/{conversation_id}")
def get_conversation(  # type: ignore[valid-type]
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    repo = ConversationRepository(session)
    conv = repo.get_by_id_for_user(conversation_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")

    # Last evidence spec and rows if present
    evidence_spec: dict[str, Any] | None = None
    evidence_rows: dict[str, Any] | None = None

    def _normalize_rows(columns: list[Any] | None, rows: list[Any] | None) -> list[dict[str, Any]]:
        """Normalize persisted table rows to a list of dicts.

        Events may have stored rows as list-of-arrays depending on the source
        (e.g., MindsDB). The frontend expects objects keyed by column name.
        """
        cols = [str(c) for c in (columns or [])]
        norm: list[dict[str, Any]] = []
        if not rows:
            return norm
        for r in rows:
            if isinstance(r, dict):
                # Ensure ordering is not required on the client
                norm.append({k: r.get(k) for k in cols} if cols else dict(r))
            elif isinstance(r, (list, tuple)):
                obj: dict[str, Any] = {}
                for i, c in enumerate(cols):
                    obj[c] = r[i] if i < len(r) else None
                norm.append(obj)
            else:
                # Fallback scalar row: attach to first column or to "value"
                key = cols[0] if cols else "value"
                norm.append({key: r})
        return norm
    for evt in conv.events:
        if evt.kind == "meta" and isinstance(evt.payload, dict) and "evidence_spec" in evt.payload:
            evidence_spec = evt.payload.get("evidence_spec")  # type: ignore[assignment]
        elif evt.kind == "rows" and isinstance(evt.payload, dict) and evt.payload.get("purpose") == "evidence":
            cols = evt.payload.get("columns") or []
            raw_rows = evt.payload.get("rows") or []
            evidence_rows = {
                "columns": cols,
                # Normalize here so the frontend gets a consistent shape in history
                "rows": _normalize_rows(cols, raw_rows),
                "row_count": evt.payload.get("row_count") or (len(raw_rows) if isinstance(raw_rows, list) else 0),
                "purpose": "evidence",
            }

    # ---- Reconstruct per-assistant message details from events timeline ----
    # We associate events emitted during streaming (plan/sql) between the last
    # user message and the following assistant message.
    messages: list[dict[str, Any]] = []
    last_user_ts = None
    # Pre-materialize events to avoid repeated attribute access
    evs = list(conv.events)
    for msg in conv.messages:
        details: dict[str, Any] | None = None
        if msg.role == "user":
            last_user_ts = msg.created_at
        else:  # assistant
            # Collect events in [last_user_ts, msg.created_at]
            if last_user_ts is not None:
                steps: list[dict[str, Any]] = []
                plan: dict[str, Any] | None = None
                for evt in evs:
                    ts = evt.created_at
                    if ts < last_user_ts or ts > msg.created_at:
                        continue
                    if evt.kind == "sql" and isinstance(evt.payload, dict):
                        steps.append(
                            {
                                "step": evt.payload.get("step"),
                                "purpose": evt.payload.get("purpose"),
                                "sql": evt.payload.get("sql"),
                            }
                        )
                    elif evt.kind == "plan" and isinstance(evt.payload, dict):
                        plan = evt.payload
                if steps or plan:
                    details = {"steps": steps} | ({"plan": plan} if plan is not None else {})
        payload: dict[str, Any] = {
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
        }
        if details:
            payload["details"] = details
        messages.append(payload)

    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "messages": messages,
        "evidence_spec": evidence_spec,
        "evidence_rows": evidence_rows,
    }
