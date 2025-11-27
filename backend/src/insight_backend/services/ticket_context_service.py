from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Iterable, List

from fastapi import HTTPException, status

from ..core.config import settings, resolve_project_path
from ..repositories.data_repository import DataRepository
from ..repositories.loop_repository import LoopRepository
from ..services.ticket_context_agent import TicketContextAgent
from ..services.ticket_utils import (
    chunk_ticket_items,
    format_ticket_context,
    prepare_ticket_entries,
    truncate_text,
)


log = logging.getLogger("insight.services.ticket_context_service")


class TicketContextService:
    def __init__(
        self,
        loop_repo: LoopRepository,
        data_repo: DataRepository,
        agent: TicketContextAgent | None = None,
    ):
        self.loop_repo = loop_repo
        self.data_repo = data_repo
        self.agent = agent or TicketContextAgent()
        self._cached_entries: list[dict[str, Any]] | None = None

    # -------- Public API --------
    def get_metadata(self, *, allowed_tables: Iterable[str] | None) -> dict[str, Any]:
        config = self._get_config()
        self._ensure_allowed(config.table_name, allowed_tables)
        entries = self._load_entries(config)
        if not entries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucun ticket exploitable avec cette configuration.",
            )
        dates = [item["date"] for item in entries]
        return {
            "table": config.table_name,
            "text_column": config.text_column,
            "date_column": config.date_column,
            "date_min": min(dates) if dates else None,
            "date_max": max(dates) if dates else None,
            "total_count": len(entries),
        }

    def build_context(
        self,
        *,
        allowed_tables: Iterable[str] | None,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, Any]:
        config = self._get_config()
        self._ensure_allowed(config.table_name, allowed_tables)
        entries = self._load_entries(config)
        if not entries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucun ticket exploitable avec cette configuration.",
            )
        filtered = self._filter_by_date(entries, date_from=date_from, date_to=date_to)
        if not filtered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucun ticket dans cette plage de dates.",
            )

        period_label = self._period_label(filtered, date_from=date_from, date_to=date_to)
        chunks = self._build_chunks(filtered)
        summary = self.agent.summarize_chunks(period_label=period_label, chunks=chunks)

        # Evidence spec + rows for UI side panel
        columns = self._derive_columns(config=config, sample=filtered)
        spec = self._build_evidence_spec(config=config, columns=columns, period_label=period_label)
        rows_payload = self._build_rows_payload(
            columns=columns,
            items=filtered,
            text_column=config.text_column,
        )

        system_message = (
            f"Contexte tickets ({period_label}) — {len(filtered)} éléments sélectionnés.\n"
            f"{summary}\n"
            "Utilise ce contexte uniquement pour répondre à l'utilisateur. Ne rajoute pas d'autres sources."
        )

        return {
            "summary": summary,
            "period_label": period_label,
            "count": len(filtered),
            "total": len(entries),
            "chunks": len(chunks),
            "table": config.table_name,
            "date_from": rows_payload.get("period", {}).get("from"),
            "date_to": rows_payload.get("period", {}).get("to"),
            "system_message": system_message,
            "evidence_spec": spec,
            "evidence_rows": rows_payload,
        }

    # -------- Internals --------
    def _get_config(self):
        config = self.loop_repo.get_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Configuration loop/tickets manquante.",
            )
        return config

    def _ensure_allowed(self, table_name: str, allowed_tables: Iterable[str] | None) -> None:
        if allowed_tables is None:
            return
        if table_name not in set(allowed_tables):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Table tickets non autorisée pour cet utilisateur.",
            )

    def _load_entries(self, config) -> list[dict[str, Any]]:
        if self._cached_entries is not None:
            return self._cached_entries
        entries = prepare_ticket_entries(
            rows=self.data_repo.read_rows(config.table_name),
            text_column=config.text_column,
            date_column=config.date_column,
        )
        self._cached_entries = entries
        return entries

    def _filter_by_date(
        self,
        entries: list[dict[str, Any]],
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict[str, Any]]:
        def _parse(dt: str | None) -> date | None:
            if not dt:
                return None
            try:
                return date.fromisoformat(dt[:10])
            except Exception:
                return None

        start = _parse(date_from)
        end = _parse(date_to)
        filtered = []
        for item in entries:
            d: date = item["date"]
            if start and d < start:
                continue
            if end and d > end:
                continue
            filtered.append(item)
        return filtered

    def _build_chunks(self, entries: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        # Pre-format ticket lines once for LLM payloads
        formatted: list[dict[str, Any]] = []
        for item in entries:
            line = f"{item['date'].isoformat()}#{item.get('ticket_id') or ''} — {truncate_text(item['text'])}"
            formatted.append(
                {
                    **item,
                    "line": line,
                    "total_count": len(entries),
                }
            )
        return chunk_ticket_items(formatted)

    def _period_label(self, entries: list[dict[str, Any]], *, date_from: str | None, date_to: str | None) -> str:
        dates = [item["date"] for item in entries]
        if not dates:
            return "période inconnue"
        start = date_from or min(dates).isoformat()
        end = date_to or max(dates).isoformat()
        return f"{start} → {end}"

    def _derive_columns(self, *, config, sample: list[dict[str, Any]]) -> list[str]:
        columns: list[str] = []
        seen: set[str] = set()
        for key in (config.text_column, config.date_column, "ticket_id"):
            if key and key not in seen:
                columns.append(key)
                seen.add(key)
        # Add remaining keys from sample raw rows to aid UI
        for item in sample[: min(10, len(sample))]:
            row = item.get("raw") or {}
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    columns.append(k)
        return columns

    def _build_evidence_spec(self, *, config, columns: list[str], period_label: str) -> dict[str, Any]:
        pk = "ticket_id" if "ticket_id" in columns else (columns[0] if columns else "id")
        spec = {
            "entity_label": "Tickets",
            "pk": pk,
            "display": {
                "title": config.text_column,
                "created_at": config.date_column,
            },
            "columns": columns,
            "limit": settings.evidence_limit_default,
            "period": {
                "from": period_label.split("→")[0].strip(),
                "to": period_label.split("→")[-1].strip(),
            },
        }
        return spec

    def _build_rows_payload(
        self,
        *,
        columns: list[str],
        items: list[dict[str, Any]],
        text_column: str,
    ) -> dict[str, Any]:
        limit = settings.evidence_limit_default
        rows: list[Dict[str, Any]] = []
        for item in items[:limit]:
            raw = item.get("raw") or {}
            row: dict[str, Any] = {}
            for col in columns:
                if col == text_column:
                    row[col] = truncate_text(raw.get(col) or item.get("text"))
                else:
                    row[col] = raw.get(col) or item.get(col)
            rows.append(row)
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(items),
            "purpose": "evidence",
            "period": {
                "from": items[-1]["date"].isoformat() if items else None,
                "to": items[0]["date"].isoformat() if items else None,
            },
        }
