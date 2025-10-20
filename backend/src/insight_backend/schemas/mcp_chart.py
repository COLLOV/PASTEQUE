from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class ChartRequest(BaseModel):
    tool: str = Field(description="Nom complet de l'outil MCP (ex: generate_bar_chart).")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passés à l'outil MCP chart.",
    )


class ChartResponse(BaseModel):
    tool: str
    chart_url: str
    spec: Dict[str, Any]
    provider: str = Field(default="mcp-server-chart")
