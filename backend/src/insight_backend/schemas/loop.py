from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..models.loop import LoopConfig, LoopSummary


LoopKind = Literal["daily", "weekly", "monthly"]


class LoopConfigRequest(BaseModel):
    table_name: str = Field(..., min_length=1)
    text_column: str = Field(..., min_length=1)
    date_column: str = Field(..., min_length=1)


class LoopConfigResponse(BaseModel):
    id: int
    table_name: str
    text_column: str
    date_column: str
    updated_at: datetime
    last_generated_at: datetime | None = None

    @classmethod
    def from_model(cls, config: LoopConfig) -> "LoopConfigResponse":
        return cls(
            id=config.id,
            table_name=config.table_name,
            text_column=config.text_column,
            date_column=config.date_column,
            updated_at=config.updated_at,
            last_generated_at=config.last_generated_at,
        )


class LoopSummaryResponse(BaseModel):
    id: int
    kind: LoopKind
    period_label: str
    period_start: date
    period_end: date
    ticket_count: int
    content: str
    created_at: datetime

    @classmethod
    def from_model(cls, summary: LoopSummary) -> "LoopSummaryResponse":
        return cls(
            id=summary.id,
            kind=summary.kind,  # type: ignore[arg-type]
            period_label=summary.period_label,
            period_start=summary.period_start,
            period_end=summary.period_end,
            ticket_count=summary.ticket_count,
            content=summary.content,
            created_at=summary.created_at,
        )


class LoopTableOverviewResponse(BaseModel):
    config: LoopConfigResponse
    daily: list[LoopSummaryResponse]
    weekly: list[LoopSummaryResponse]
    monthly: list[LoopSummaryResponse]
    last_generated_at: datetime | None = None


class LoopOverviewResponse(BaseModel):
    items: list[LoopTableOverviewResponse]
