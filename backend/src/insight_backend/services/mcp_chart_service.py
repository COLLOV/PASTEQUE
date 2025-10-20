from __future__ import annotations

import csv
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import logging

from openai.types.chat import ChatCompletion as OpenAIChatCompletion
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ..core.config import settings
from ..integrations.mcp_manager import MCPManager, MCPServerSpec
from ..repositories.data_repository import DataRepository


class ChartGenerationError(RuntimeError):
    """Raised when chart generation via MCP fails."""


log = logging.getLogger("insight.services.mcp_chart")


class ChartAgentOutput(BaseModel):
    chart_url: str
    tool_name: str
    chart_title: str | None = None
    chart_description: str | None = None
    chart_spec: Dict[str, Any] | None = None


@dataclass(slots=True)
class ChartAgentDeps:
    repo: DataRepository
    max_rows: int = 500

    def tables_catalog(self) -> list[tuple[str, list[str]]]:
        catalog: list[tuple[str, list[str]]] = []
        for table in self.repo.list_tables():
            try:
                columns = [col for col, _ in self.repo.get_schema(table)]
            except FileNotFoundError:
                continue
            catalog.append((table, columns))
        catalog.sort(key=lambda item: item[0])
        return catalog

    def describe_catalog(self) -> str:
        lines = ["Jeux de données disponibles dans data/raw :"]
        for name, columns in self.tables_catalog():
            preview = ", ".join(columns[:8])
            if len(columns) > 8:
                preview += ", …"
            lines.append(f"- {name} (colonnes: {preview})")
        return "\n".join(lines)

    def load_rows(
        self,
        dataset: str,
        columns: list[str] | None = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        path = self._resolve_table_path(dataset)
        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        selected_columns: list[str] | None = None
        rows: list[dict[str, str]] = []
        max_items = max(1, min(limit, self.max_rows))

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            fieldnames = reader.fieldnames or []
            selected_columns = columns or fieldnames
            if not selected_columns:
                raise ChartGenerationError(
                    f"Aucune colonne détectée dans {path.name}."
                )

            for row in reader:
                record = {col: (row.get(col) or "").strip() for col in selected_columns}
                rows.append(record)
                if len(rows) >= max_items:
                    break

        return {
            "dataset": self._dataset_name(path),
            "columns": selected_columns,
            "rows": rows,
        }

    def aggregate_counts(
        self,
        dataset: str,
        column: str,
        filters: Dict[str, Any] | None = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        path = self._resolve_table_path(dataset)
        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        counter: Counter[str] = Counter()
        applied_limit = max(1, limit)

        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if column not in (reader.fieldnames or []):
                available = ", ".join(reader.fieldnames or [])
                raise ChartGenerationError(
                    f"Colonne '{column}' introuvable dans {self._dataset_name(path)}. Colonnes: {available}"
                )

            for row in reader:
                if filters and not self._matches_filters(row, filters):
                    continue
                key = (row.get(column) or "").strip()
                if not key:
                    continue
                counter[key] += 1

        if not counter:
            return {
                "dataset": self._dataset_name(path),
                "column": column,
                "filters": filters or {},
                "counts": [],
            }

        items = counter.most_common(applied_limit)
        data = [
            {"category": label, "value": count}
            for label, count in items
        ]
        return {
            "dataset": self._dataset_name(path),
            "column": column,
            "filters": filters or {},
            "counts": data,
        }

    def _resolve_table_path(self, dataset: str) -> Path:
        base = Path(self.repo.tables_dir)
        candidates: list[Path] = []
        name = dataset.strip()
        if not name:
            raise ChartGenerationError("Paramètre 'dataset' vide pour chargement de données.")

        direct = base / name
        if direct.exists():
            candidates.append(direct)

        for ext in (".csv", ".tsv"):
            candidates.append(base / f"{name}{ext}")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate

        raise ChartGenerationError(
            f"Dataset introuvable: {name}. Vérifiez data/raw/."
        )

    def _matches_filters(self, row: dict[str, str], filters: Dict[str, Any]) -> bool:
        for key, expected in filters.items():
            value = (row.get(key) or "").strip()
            if isinstance(expected, list):
                normalized = {str(item).strip() for item in expected}
                if value not in normalized:
                    return False
            else:
                if value != str(expected).strip():
                    return False
        return True

    @staticmethod
    def _dataset_name(path: Path) -> str:
        return path.name


@dataclass(slots=True)
class ChartResult:
    prompt: str
    chart_url: str
    tool_name: str
    chart_title: str | None
    chart_description: str | None
    chart_spec: Dict[str, Any] | None


class LenientOpenAIChatModel(OpenAIChatModel):
    """OpenAI chat model that tolerates missing metadata from compatible backends."""

    def _process_response(self, response: OpenAIChatCompletion | str) -> ModelResponse:  # type: ignore[override]
        if isinstance(response, OpenAIChatCompletion) and not getattr(response, "object", None):
            response.object = "chat.completion"
        return super()._process_response(response)


class ChartGenerationService:
    """Generates charts dynamically through the MCP chart server."""

    _DEFAULT_MAX_ROWS = 400

    def __init__(self, data_root: Path | None = None) -> None:
        self._data_root = Path(data_root or settings.data_root).resolve()
        self._raw_root = self._data_root / "raw"
        self._chart_spec = self._resolve_chart_spec()

    async def generate_chart(self, prompt: str) -> ChartResult:
        if not prompt.strip():
            raise ChartGenerationError("La requête utilisateur est vide.")

        provider, model_name = self._build_provider()
        env = os.environ.copy()
        env.update(self._chart_spec.env or {})

        server = MCPServerStdio(
            self._chart_spec.command,
            self._chart_spec.args,
            env=env,
            tool_prefix=self._chart_spec.name,
            timeout=30,
            read_timeout=300,
        )

        model = LenientOpenAIChatModel(model_name=model_name, provider=provider)
        agent = Agent(
            model,
            name="mcp-chart",
            instructions=self._base_instructions(self._chart_spec.name),
            deps_type=ChartAgentDeps,
            output_type=ChartAgentOutput,
            toolsets=[server],
        )

        @agent.tool
        async def load_dataset(  # type: ignore[no-untyped-def]
            ctx: RunContext[ChartAgentDeps],
            dataset: str,
            columns: list[str] | None = None,
            limit: int = 200,
        ) -> Dict[str, Any]:
            """Charge les lignes d'un CSV (max 'limit') pour inspection."""
            return ctx.deps.load_rows(dataset, columns, limit)

        @agent.tool
        async def aggregate_counts(  # type: ignore[no-untyped-def]
            ctx: RunContext[ChartAgentDeps],
            dataset: str,
            column: str,
            filters: Dict[str, Any] | None = None,
            limit: int = 30,
        ) -> Dict[str, Any]:
            """Calcule une distribution par catégories sur une colonne."""
            return ctx.deps.aggregate_counts(dataset, column, filters or {}, limit)

        @agent.instructions
        async def dataset_catalog(ctx: RunContext[ChartAgentDeps]) -> str:
            return ctx.deps.describe_catalog()

        deps = ChartAgentDeps(
            repo=DataRepository(tables_dir=self._raw_root),
            max_rows=self._DEFAULT_MAX_ROWS,
        )

        try:
            async with agent:
                result = await agent.run(prompt, deps=deps)
        except UnexpectedModelBehavior as exc:
            log.exception("Réponse LLM incompatible pour la génération de graphiques")
            raise ChartGenerationError(f"Réponse LLM incompatible: {exc}") from exc
        except Exception as exc:  # pragma: no cover - dépend des intégrations externes
            log.exception("Échec lors de la génération de graphique via MCP")
            raise ChartGenerationError(str(exc)) from exc

        output = result.output
        if not output.chart_url:
            raise ChartGenerationError("L'agent n'a pas fourni d'URL de graphique.")

        return ChartResult(
            prompt=prompt,
            chart_url=output.chart_url,
            tool_name=output.tool_name,
            chart_title=output.chart_title,
            chart_description=output.chart_description,
            chart_spec=output.chart_spec,
        )

    def _resolve_chart_spec(self) -> MCPServerSpec:
        manager = MCPManager()
        for spec in manager.list_servers():
            if spec.name in {"chart", "mcp-server-chart"}:
                return spec
        raise ChartGenerationError(
            "Serveur MCP 'chart' introuvable. Vérifiez MCP_CONFIG_PATH ou MCP_SERVERS_JSON."
        )

    def _build_provider(self) -> tuple[OpenAIProvider, str]:
        if settings.llm_mode not in {"local", "api"}:
            raise ChartGenerationError("LLM_MODE doit valoir 'local' ou 'api'.")

        if settings.llm_mode == "local":
            base_url = (settings.vllm_base_url or "").rstrip("/")
            model_name = settings.z_local_model
            api_key = None
        else:
            base_url = (settings.openai_base_url or "").rstrip("/")
            model_name = settings.llm_model
            api_key = settings.openai_api_key

        if not base_url or not model_name:
            raise ChartGenerationError(
                "Configuration LLM incomplète pour la génération de graphiques."
            )

        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
        return provider, model_name

    @staticmethod
    def _base_instructions(tool_prefix: str | None) -> str:
        prefix_hint = (
            f"Les outils du serveur MCP sont exposés sous le préfixe '{tool_prefix}_'."
            if tool_prefix
            else "Les outils du serveur MCP sont disponibles sans préfixe spécifique."
        )
        return (
            "Tu es un analyste data. Analyse précisément la requête utilisateur,"\
            " inspecte les CSV locaux (data/raw) à l'aide des outils Python fournis,"
            " puis génère un graphique via le serveur MCP Chart. "
            + prefix_hint
            + "\n"
            "Processus obligatoire :\n"
            "1. Identifier les colonnes pertinentes grâce aux outils load_dataset et aggregate_counts.\n"
            "2. Choisir l'outil de visualisation MCP adapté (ex. generate_bar_chart).\n"
            "3. Fournir au MCP un payload JSON propre incluant les données préparées.\n"
            "4. Produire un ChartAgentOutput strictement valide avec :\n"
            "   - chart_url : URL retournée par le MCP\n"
            "   - tool_name : nom exact de l'outil MCP utilisé\n"
            "   - chart_title / chart_description : résumé concis\n"
            "   - chart_spec : payload JSON transmis au MCP (incluant type, data, options).\n"
            "N'ajoute aucun texte libre en dehors de ce schéma."
        )
