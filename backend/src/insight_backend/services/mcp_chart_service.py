from __future__ import annotations

from typing import Any, Dict

import httpx

from ..integrations.mcp_manager import MCPManager, MCPServerSpec


class ChartGenerationError(RuntimeError):
    """Raised when chart generation via MCP fails."""


class ChartGenerationService:
    """Delegate chart generation to the configured MCP chart server."""

    TOOL_TO_CHART_TYPE: Dict[str, str] = {
        "generate_line_chart": "line",
        "generate_bar_chart": "bar",
        "generate_column_chart": "column",
        "generate_pie_chart": "pie",
        "generate_area_chart": "area",
        "generate_scatter_chart": "scatter",
        "generate_histogram_chart": "histogram",
        "generate_treemap_chart": "treemap",
        "generate_radar_chart": "radar",
        "generate_sankey_chart": "sankey",
        "generate_liquid_chart": "liquid",
        "generate_boxplot_chart": "boxplot",
        "generate_funnel_chart": "funnel",
        "generate_bar_chart_grouped": "bar",
    }

    DEFAULT_VIS_SERVER = "https://antv-studio.alipay.com/api/gpt-vis"

    def __init__(self) -> None:
        spec = self._resolve_chart_spec()
        self._env_overrides = spec.env or {}
        self._vis_server = self._env_overrides.get("VIS_REQUEST_SERVER") or self.DEFAULT_VIS_SERVER
        self._service_id = self._env_overrides.get("SERVICE_ID")

    def _resolve_chart_spec(self) -> MCPServerSpec:
        manager = MCPManager()
        for spec in manager.list_servers():
            if spec.name in {"chart", "mcp-server-chart"}:
                return spec
        raise ChartGenerationError(
            "Serveur MCP 'chart' introuvable. Vérifiez MCP_CONFIG_PATH ou MCP_SERVERS_JSON."
        )

    def generate(self, tool: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ChartGenerationError("Le champ 'arguments' doit être un objet JSON.")

        chart_type = self._resolve_chart_type(tool)
        payload: Dict[str, Any] = {
            "type": chart_type,
            "source": "mcp-server-chart",
            **arguments,
        }
        if self._service_id:
            payload.setdefault("serviceId", self._service_id)

        try:
            response = httpx.post(self._vis_server, json=payload, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ChartGenerationError(
                f"Appel au serveur MCP chart impossible ({exc})."
            ) from exc

        data = response.json()
        if not data.get("success"):
            message = data.get("errorMessage") or "Le serveur MCP chart a rejeté la requête."
            raise ChartGenerationError(message)

        chart_url = data.get("resultObj")
        if not chart_url:
            raise ChartGenerationError("Le serveur MCP chart n'a pas renvoyé d'URL de graphique.")

        return {
            "tool": tool,
            "chart_url": chart_url,
            "spec": payload,
            "provider": "mcp-server-chart",
        }

    def _resolve_chart_type(self, tool: str) -> str:
        normalized = tool.strip()
        if normalized in self.TOOL_TO_CHART_TYPE:
            return self.TOOL_TO_CHART_TYPE[normalized]
        if normalized.startswith("generate_") and normalized.endswith("_chart"):
            return normalized.replace("generate_", "").replace("_chart", "")
        raise ChartGenerationError(f"Outil MCP chart non supporté: {tool}")
