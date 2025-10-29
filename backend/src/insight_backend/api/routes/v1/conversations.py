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
    for evt in conv.events:
        if evt.kind == "meta" and isinstance(evt.payload, dict) and "evidence_spec" in evt.payload:
            evidence_spec = evt.payload.get("evidence_spec")  # type: ignore[assignment]
        elif evt.kind == "rows" and isinstance(evt.payload, dict) and evt.payload.get("purpose") == "evidence":
            evidence_rows = {
                "columns": evt.payload.get("columns") or [],
                "rows": evt.payload.get("rows") or [],
                "row_count": evt.payload.get("row_count"),
                "purpose": "evidence",
            }

    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in conv.messages
        ],
        "evidence_spec": evidence_spec,
        "evidence_rows": evidence_rows,
    }

