from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import HTTPException, status

from ..core.config import settings
from ..repositories.data_repository import DataRepository
from ..repositories.loop_repository import LoopRepository
from ..services.looper_agent import LooperAgent
from ..models.loop import LoopConfig, LoopSummary
from .ticket_utils import (
    chunk_ticket_items,
    format_ticket_context,
    prepare_ticket_entries,
)


log = logging.getLogger("insight.services.loop")


class LoopService:
    def __init__(
        self,
        repo: LoopRepository,
        data_repo: DataRepository,
        agent: LooperAgent | None = None,
    ):
        self.repo = repo
        self.data_repo = data_repo
        self.agent = agent or LooperAgent()

    # --- Public API ----------------------------------------------------
    def get_overview(self) -> tuple[LoopConfig | None, list[LoopSummary], list[LoopSummary]]:
        config = self.repo.get_config()
        if not config:
            return None, [], []
        weekly = self.repo.list_by_kind(kind="weekly", config_id=config.id)[:1]
        monthly = self.repo.list_by_kind(kind="monthly", config_id=config.id)[:1]
        return config, weekly, monthly

    def save_config(self, *, table_name: str, text_column: str, date_column: str) -> LoopConfig:
        self._validate_columns(table_name=table_name, text_column=text_column, date_column=date_column)
        existing = self.repo.get_config()
        previous = (
            (existing.table_name, existing.text_column, existing.date_column)
            if existing
            else None
        )
        config = self.repo.save_config(
            table_name=table_name,
            text_column=text_column,
            date_column=date_column,
        )
        if previous and previous != (config.table_name, config.text_column, config.date_column):
            # Purge les résumés obsolètes pour éviter toute confusion
            self.repo.replace_summaries(config=config, items=[])
        return config

    def regenerate(self) -> tuple[LoopConfig, list[LoopSummary], list[LoopSummary]]:
        config = self.repo.get_config()
        if not config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucune configuration loop n'est définie.",
            )

        try:
            rows = self.data_repo.read_rows(config.table_name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        entries = prepare_ticket_entries(rows=rows, text_column=config.text_column, date_column=config.date_column)
        if not entries:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucun ticket exploitable avec cette configuration.",
            )

        weekly_groups = self._group_by_week(entries)
        monthly_groups = self._group_by_month(entries)
        if not weekly_groups and not monthly_groups:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Impossible de constituer des groupes hebdomadaires ou mensuels avec les données présentes.",
            )

        payloads: list[dict] = []
        for group in weekly_groups:
            content = self._summarize_group(group, kind="weekly")
            payloads.append(content)

        for group in monthly_groups:
            content = self._summarize_group(group, kind="monthly")
            payloads.append(content)

        saved = self.repo.replace_summaries(config=config, items=payloads)
        now = datetime.now(timezone.utc)
        self.repo.touch_generated(config_id=config.id, ts=now)

        weekly = [item for item in saved if item.kind == "weekly"][:1]
        monthly = [item for item in saved if item.kind == "monthly"][:1]
        return config, weekly, monthly

    # --- Helpers -------------------------------------------------------
    def _validate_columns(self, *, table_name: str, text_column: str, date_column: str) -> None:
        try:
            cols = [name for name, _ in self.data_repo.get_schema(table_name)]
        except FileNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        missing: list[str] = []
        for col in (text_column, date_column):
            if col not in cols:
                missing.append(col)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Colonnes manquantes dans {table_name}: {', '.join(missing)}",
            )

    def _group_by_week(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for item in entries:
            d: date = item["date"]
            iso = d.isocalendar()
            key = (iso.year, iso.week)
            buckets.setdefault(key, []).append(item)
        groups: list[dict[str, Any]] = []
        for (year, week), items in buckets.items():
            start = date.fromisocalendar(year, week, 1)
            end = start + timedelta(days=6)
            groups.append(
                {
                    "label": f"{year}-S{week:02d}",
                    "start": start,
                    "end": end,
                    "items": items,
                }
            )
        groups.sort(key=lambda g: g["start"], reverse=True)
        limit = max(1, int(settings.loop_max_weeks))
        return groups[:limit]

    def _group_by_month(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for item in entries:
            d: date = item["date"]
            key = (d.year, d.month)
            buckets.setdefault(key, []).append(item)
        groups: list[dict[str, Any]] = []
        for (year, month), items in buckets.items():
            start = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end = date(year, month, last_day)
            groups.append(
                {
                    "label": f"{year}-{month:02d}",
                    "start": start,
                    "end": end,
                    "items": items,
                }
            )
        groups.sort(key=lambda g: g["start"], reverse=True)
        limit = max(1, int(settings.loop_max_months))
        return groups[:limit]

    def _summarize_group(self, group: Dict[str, Any], *, kind: str) -> dict:
        items = group["items"]
        chunks = chunk_ticket_items(items)
        partial_summaries: list[str] = []

        for idx, chunk in enumerate(chunks, start=1):
            lines, truncated = format_ticket_context(chunk)
            if truncated:
                log.warning(
                    "Context %s %s tronqué à %d tickets (chunk=%d/%d total_chunk_tickets=%d)",
                    kind,
                    group["label"],
                    len(lines),
                    idx,
                    len(chunks),
                    len(chunk),
                )
            partial = self.agent.summarize(
                period_label=f"{group['label']} (part {idx}/{len(chunks)})",
                period_start=group["start"],
                period_end=group["end"],
                tickets=lines,
                total_tickets=len(chunk),
            )
            partial_summaries.append(partial)

        if len(partial_summaries) == 1:
            final_content = partial_summaries[0]
        else:
            tickets = [
                f"Synthèse partielle {i+1}/{len(partial_summaries)} : {text}"
                for i, text in enumerate(partial_summaries)
            ]
            final_content = self.agent.summarize(
                period_label=f"{group['label']} (fusion)",
                period_start=group["start"],
                period_end=group["end"],
                tickets=tickets,
                total_tickets=len(items),
            )
        return {
            "kind": kind,
            "period_label": group["label"],
            "period_start": group["start"],
            "period_end": group["end"],
            "ticket_count": len(items),
            "content": final_content,
        }
