from __future__ import annotations

from datetime import datetime
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..models.chart import Chart


class ChartSaveRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    chart_url: str = Field(..., min_length=1)
    tool_name: str | None = None
    chart_title: str | None = None
    chart_description: str | None = None
    chart_spec: dict[str, Any] | None = None


class ChartResponse(BaseModel):
    id: int
    prompt: str
    chart_url: str
    tool_name: str | None = None
    chart_title: str | None = None
    chart_description: str | None = None
    chart_spec: dict[str, Any] | None = None
    created_at: datetime
    owner_username: str

    @classmethod
    def from_model(cls, chart: "Chart", owner_username: str | None = None) -> "ChartResponse":
        username = owner_username or (chart.user.username if chart.user else "")
        return cls(
            id=chart.id,
            prompt=chart.prompt,
            chart_url=chart.chart_url,
            tool_name=chart.tool_name,
            chart_title=chart.chart_title,
            chart_description=chart.chart_description,
            chart_spec=chart.chart_spec,
            created_at=chart.created_at,
            owner_username=username,
        )
