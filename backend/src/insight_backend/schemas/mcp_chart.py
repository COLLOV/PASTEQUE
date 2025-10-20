from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class ChartRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Instruction utilisateur pour le graphique")


class ChartResponse(BaseModel):
    prompt: str
    chart_url: str
    tool_name: str
    chart_title: str | None = None
    chart_description: str | None = None
    chart_spec: Dict[str, Any] | None = None
