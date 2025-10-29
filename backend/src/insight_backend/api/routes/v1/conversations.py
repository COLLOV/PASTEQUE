from __future__ import annotations

from typing import Any, List, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ....core.database import get_session
from ....models.user import User
from ....repositories.conversation_repository import ConversationRepository
from ....core.security import get_current_user
from ....integrations.mindsdb_client import MindsDBClient
from ....core.config import settings


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

    # ---- Build a unified, time-ordered stream mixing messages and chart events ----
    entries: List[Dict[str, Any]] = []
    # 1) Start with plain messages and attach details (plan/sql) to assistant answers
    last_user_ts = None
    evs = list(conv.events)
    for msg in conv.messages:
        details: dict[str, Any] | None = None
        if msg.role == "user":
            last_user_ts = msg.created_at
        else:
            if last_user_ts is not None:
                steps: list[dict[str, Any]] = []
                plan: dict[str, Any] | None = None
                for evt in evs:
                    ts = evt.created_at
                    if ts < last_user_ts or ts > msg.created_at:
                        continue
                    if evt.kind == "sql" and isinstance(evt.payload, dict):
                        steps.append({
                            "step": evt.payload.get("step"),
                            "purpose": evt.payload.get("purpose"),
                            "sql": evt.payload.get("sql"),
                        })
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
        entries.append({"created_at": msg.created_at.isoformat(), "payload": payload})

    # 2) Add chart events as synthetic assistant messages
    for evt in conv.events:
        if evt.kind != "chart" or not isinstance(evt.payload, dict):
            continue
        p = evt.payload
        chart_url = p.get("chart_url")
        if not isinstance(chart_url, str) or not chart_url:
            continue
        payload = {
            "role": "assistant",
            "content": "",
            "created_at": evt.created_at.isoformat(),
            "chart_url": chart_url,
            "chart_title": p.get("chart_title"),
            "chart_description": p.get("chart_description"),
            "chart_tool": p.get("tool_name") or p.get("chart_tool"),
            "chart_spec": p.get("chart_spec"),
        }
        entries.append({"created_at": evt.created_at.isoformat(), "payload": payload})

    # 3) Sort entries by time (ISO 8601 sort is chronological)
    entries.sort(key=lambda x: x["created_at"])  # type: ignore[no-any-return]
    messages: list[dict[str, Any]] = [e["payload"] for e in entries]

    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
        "messages": messages,
        "evidence_spec": evidence_spec,
        "evidence_rows": evidence_rows,
    }


@router.get("/{conversation_id}/dataset")
def get_message_dataset(  # type: ignore[valid-type]
    conversation_id: int,
    message_index: int = Query(..., ge=0),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Re-exécute la dernière requête SQL liée à un message assistant et renvoie un petit dataset.

    Utilise les événements persistés (kind="sql") entre le dernier message user et le message assistant ciblé.
    Les requêtes d'évidence sont ignorées.
    """
    repo = ConversationRepository(session)
    conv = repo.get_by_id_for_user(conversation_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    if message_index < 0 or message_index >= len(conv.messages):
        raise HTTPException(status_code=400, detail="Index de message invalide")
    msg = conv.messages[message_index]
    if msg.role != "assistant":
        raise HTTPException(status_code=400, detail="Le message ciblé n'est pas une réponse assistant")

    # Délimiter la fenêtre temporelle: après le dernier message user précédent et avant/à l'horodatage du message assistant
    start_ts = None
    for m in reversed(conv.messages[: message_index]):
        if m.role == "user":
            start_ts = m.created_at
            break
    end_ts = msg.created_at

    sql_text: str | None = None
    step: int | None = None
    purpose: str | None = None
    for evt in conv.events:
        ts = evt.created_at
        if start_ts and ts < start_ts:
            continue
        if ts > end_ts:
            continue
        if evt.kind == "sql" and isinstance(evt.payload, dict):
            if evt.payload.get("purpose") == "evidence":
                continue
            # Retenir le dernier SQL non-évidence de la fenêtre
            sql_text = evt.payload.get("sql") or sql_text
            step = evt.payload.get("step") if isinstance(evt.payload.get("step"), int) else step
            purpose = evt.payload.get("purpose") or purpose

    if not sql_text or not isinstance(sql_text, str):
        raise HTTPException(status_code=404, detail="Aucune requête SQL associée à ce message")

    # Sécuriser et plafonner
    s = sql_text.strip()
    if not s.lower().startswith("select"):
        raise HTTPException(status_code=400, detail="Requête non sélectionnable")
    if any(k in s.lower() for k in [";", " insert ", " update ", " delete ", " alter ", " drop ", " create "]):
        raise HTTPException(status_code=400, detail="Requête SQL non autorisée")
    if " limit " not in s.lower():
        s = f"{s} LIMIT {settings.evidence_limit_default}"

    client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)
    data = client.sql(s)

    # Normaliser le résultat (inspiré de ChatService._normalize_result)
    rows: list[Any] = []
    columns: list[Any] = []
    if isinstance(data, dict):
        if data.get("type") == "table":
            columns = data.get("column_names") or []
            rows = data.get("data") or []
        if not rows:
            rows = data.get("result", {}).get("rows") or data.get("rows") or rows
        if not columns:
            columns = data.get("result", {}).get("columns") or data.get("columns") or columns

    # Convertir en objets côté API pour le front
    cols = [str(c) for c in (columns or [])]
    def _to_obj_row(r: Any) -> dict[str, Any]:
        if isinstance(r, dict):
            return {k: r.get(k) for k in cols} if cols else dict(r)
        if isinstance(r, (list, tuple)):
            obj: dict[str, Any] = {}
            for i, c in enumerate(cols):
                obj[c] = r[i] if i < len(r) else None
            return obj
        key = cols[0] if cols else "value"
        return {key: r}
    obj_rows = [_to_obj_row(r) for r in (rows or [])]

    return {
        "dataset": {
            "sql": s,
            "columns": cols,
            "rows": obj_rows,
            "row_count": len(obj_rows),
            "step": step,
            "description": purpose,
        }
    }


@router.post("/{conversation_id}/chart")
def append_chart_event(  # type: ignore[valid-type]
    conversation_id: int,
    payload: dict[str, Any],
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Persist a chart generation event so charts reappear in conversation history.

    Body fields (subset used): chart_url (required), tool_name, chart_title, chart_description, chart_spec.
    """
    repo = ConversationRepository(session)
    conv = repo.get_by_id_for_user(conversation_id, current_user.id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    url = payload.get("chart_url")
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=400, detail="chart_url manquant")
    safe_payload = {
        "chart_url": url,
        "tool_name": payload.get("tool_name"),
        "chart_title": payload.get("chart_title"),
        "chart_description": payload.get("chart_description"),
        "chart_spec": payload.get("chart_spec"),
    }
    evt = repo.add_event(conversation_id=conversation_id, kind="chart", payload=safe_payload)
    session.commit()
    return {"id": evt.id, "created_at": evt.created_at.isoformat()}
