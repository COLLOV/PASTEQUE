from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class GeneratedChart(BaseModel):
    key: str
    dataset: str
    title: str
    description: str | None = None
    tool: str
    chart_url: str
    spec: Dict[str, Any]


class ChartCollectionResponse(BaseModel):
    charts: List[GeneratedChart]
    metadata: Dict[str, Any] | None = None

