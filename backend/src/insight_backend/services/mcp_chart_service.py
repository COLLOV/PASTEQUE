from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List

import httpx

from ..core.config import settings
from ..integrations.mcp_manager import MCPManager, MCPServerSpec


class ChartGenerationError(RuntimeError):
    """Raised when chart generation via MCP fails."""


@dataclass(slots=True)
class ChartDefinition:
    key: str
    dataset: str
    title: str
    description: str
    tool: str
    arguments: Dict[str, Any]


class ChartGenerationService:
    """Generates charts based on local CSV data using the MCP chart configuration."""

    TOOL_TO_CHART_TYPE = {
        "generate_line_chart": "line",
        "generate_bar_chart": "bar",
        "generate_pie_chart": "pie",
    }
    DEFAULT_VIS_SERVER = "https://antv-studio.alipay.com/api/gpt-vis"

    def __init__(self, data_root: Path | None = None) -> None:
        self._data_root = Path(data_root or settings.data_root).resolve()
        self._raw_root = self._data_root / "raw"
        self._chart_spec = self._resolve_chart_spec()
        self._vis_server = self._chart_spec.env.get("VIS_REQUEST_SERVER") or self.DEFAULT_VIS_SERVER
        self._service_id = self._chart_spec.env.get("SERVICE_ID")
        self._builders = {
            "nps": self._build_nps_trend_chart,
            "subscriptions": self._build_subscriptions_channel_chart,
            "support": self._build_support_resolution_chart,
        }

    def _resolve_chart_spec(self) -> MCPServerSpec:
        manager = MCPManager()
        for spec in manager.list_servers():
            if spec.name in {"chart", "mcp-server-chart"}:
                return spec
        raise ChartGenerationError(
            "Serveur MCP 'chart' introuvable. Vérifiez MCP_CONFIG_PATH ou MCP_SERVERS_JSON."
        )

    def available(self) -> List[Dict[str, Any]]:
        catalog = self._build_catalog()
        results: List[Dict[str, Any]] = []
        for command, definition in catalog.items():
            results.append(
                {
                    "command": command,
                    "key": definition.key,
                    "title": definition.title,
                    "dataset": definition.dataset,
                    "description": definition.description,
                }
            )
        return results

    def generate(self, selectors: Iterable[str] | None = None) -> List[Dict[str, Any]]:
        catalog = self._build_catalog()
        selected: List[tuple[str, ChartDefinition]] = []

        if selectors:
            for selector in selectors:
                slug = selector.strip().lower()
                match: tuple[str, ChartDefinition] | None = None
                for command, definition in catalog.items():
                    if slug in {command.lower(), definition.key.lower()}:
                        match = (command, definition)
                        break
                if not match:
                    raise ChartGenerationError(f"Graphique inconnu: {selector}")
                if match not in selected:
                    selected.append(match)
        else:
            selected = list(catalog.items())

        charts: List[Dict[str, Any]] = []
        for command, definition in selected:
            chart_payload = self._generate_single_chart(definition)
            charts.append(
                {
                    "command": command,
                    "key": definition.key,
                    "dataset": definition.dataset,
                    "title": definition.title,
                    "description": definition.description,
                    "tool": definition.tool,
                    "chart_url": chart_payload["chart_url"],
                    "spec": chart_payload["spec"],
                }
            )

        return charts

    def _build_catalog(self) -> Dict[str, ChartDefinition]:
        catalog: Dict[str, ChartDefinition] = {}
        for command, builder in self._builders.items():
            catalog[command] = builder()
        return catalog

    def _generate_single_chart(self, definition: ChartDefinition) -> Dict[str, Any]:
        chart_type = self.TOOL_TO_CHART_TYPE.get(definition.tool)
        if not chart_type:
            raise ChartGenerationError(f"Outil MCP non pris en charge: {definition.tool}")

        payload = dict(definition.arguments)
        payload.update({"type": chart_type, "source": "mcp-server-chart"})
        if self._service_id:
            payload.setdefault("serviceId", self._service_id)

        try:
            response = httpx.post(self._vis_server, json=payload, timeout=30.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - dépend du réseau
            raise ChartGenerationError(
                f"Appel au service de visualisation impossible ({definition.tool}): {exc}"
            ) from exc

        data = response.json()
        if not data.get("success"):
            message = data.get("errorMessage") or "Le service distant a rejeté la requête."
            raise ChartGenerationError(
                f"Le service de visualisation a renvoyé une erreur pour {definition.tool}: {message}"
            )

        chart_url = data.get("resultObj")
        if not chart_url:
            raise ChartGenerationError("Le service de visualisation n'a pas fourni d'URL de graphique.")

        spec = {"type": chart_type, **definition.arguments}
        return {"chart_url": chart_url, "spec": spec}

    def _read_csv(self, filename: str) -> Iterable[Dict[str, str]]:
        path = self._raw_root / filename
        if not path.exists():
            raise ChartGenerationError(f"Dataset introuvable: {path}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield row

    def _build_nps_trend_chart(self) -> ChartDefinition:
        monthly: Dict[str, Dict[str, Decimal | int]] = defaultdict(
            lambda: {"sum": Decimal("0"), "count": 0}
        )
        for row in self._read_csv("myfeelback_nps.csv"):
            date_raw = (row.get("date_feedback") or "").strip()
            score_raw = (row.get("nps_score") or "").strip()
            if not date_raw or len(date_raw) < 7 or not score_raw:
                continue
            month = date_raw[:7]
            try:
                score = Decimal(score_raw)
            except InvalidOperation:
                continue
            bucket = monthly[month]
            bucket["sum"] = bucket["sum"] + score  # type: ignore[assignment]
            bucket["count"] = int(bucket["count"]) + 1  # type: ignore[assignment]

        data = []
        for month in sorted(monthly.keys()):
            bucket = monthly[month]
            count = int(bucket["count"])
            if count == 0:
                continue
            average = (bucket["sum"] / count).quantize(Decimal("0.01"))
            data.append({"time": month, "value": float(average)})

        if not data:
            raise ChartGenerationError("Aucune donnée exploitable pour le NPS mensuel.")

        return ChartDefinition(
            key="nps_monthly_trend",
            dataset="myfeelback_nps.csv",
            title="Évolution du NPS moyen",
            description="Score NPS moyen par mois basé sur les retours clients.",
            tool="generate_line_chart",
            arguments={
                "data": data,
                "title": "NPS moyen par mois",
                "axisXTitle": "Mois",
                "axisYTitle": "Score moyen",
            },
        )

    def _build_subscriptions_channel_chart(self) -> ChartDefinition:
        counter: Counter[str] = Counter()
        for row in self._read_csv("myfeelback_souscriptions.csv"):
            channel = (row.get("canal") or "").strip()
            if channel:
                counter[channel] += 1

        data = [
            {"category": channel, "value": count}
            for channel, count in counter.most_common()
            if count > 0
        ]

        if not data:
            raise ChartGenerationError("Aucune donnée exploitable pour les canaux de souscription.")

        return ChartDefinition(
            key="subscriptions_by_channel",
            dataset="myfeelback_souscriptions.csv",
            title="Souscriptions par canal",
            description="Volume de souscriptions par canal de vente.",
            tool="generate_bar_chart",
            arguments={
                "data": data,
                "title": "Souscriptions par canal",
                "axisXTitle": "Canal de souscription",
                "axisYTitle": "Nombre de souscriptions",
                "stack": False,
                "group": False,
            },
        )

    def _build_support_resolution_chart(self) -> ChartDefinition:
        counter: Counter[str] = Counter()
        for row in self._read_csv("myfeelback_service_client.csv"):
            solved = (row.get("probleme_resolu") or "").strip() or "Inconnu"
            counter[solved] += 1

        data = [
            {"category": label, "value": count}
            for label, count in counter.items()
            if count > 0
        ]

        if not data:
            raise ChartGenerationError("Aucune donnée exploitable sur la résolution du support.")

        data.sort(key=lambda item: item["value"], reverse=True)

        return ChartDefinition(
            key="support_resolution_ratio",
            dataset="myfeelback_service_client.csv",
            title="Résolution des demandes",
            description="Part des demandes résolues vs non résolues au support client.",
            tool="generate_pie_chart",
            arguments={
                "data": data,
                "title": "Résolution au support client",
                "innerRadius": 0.0,
            },
        )
