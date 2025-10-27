from __future__ import annotations

import asyncio
import json
import logging
import textwrap
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.mcp import MCPServerStdio

from ..core.config import settings
from ..integrations.mcp_manager import MCPManager, MCPServerSpec
from ..integrations.neo4j_client import Neo4jClient, Neo4jClientError, Neo4jResult
from .neo4j_ingest import Neo4jIngestionService


log = logging.getLogger("insight.services.neo4j_graph")

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2})?$")


class Neo4jGraphError(RuntimeError):
    """Raised when graph reasoning fails."""


class GraphAgentOutput(BaseModel):
    answer: str
    cypher: str


class GraphAnswerRewrite(BaseModel):
    answer: str


@dataclass(slots=True)
class Neo4jGraphResult:
    answer: str
    cypher: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    model: str


class Neo4jGraphService:
    """Execute semantic graph queries through the Neo4j MCP server."""

    _INSTRUCTIONS = textwrap.dedent(
        """
        Tu analyses un graphe Neo4j contenant les entités suivantes:
        - (Client {{id, last_seen}})
        - (AgencyFeedback {{feedback_id, agence, motif_visite, note_globale, ...}})
        - (AppFeedback {{feedback_id, version_app, fonctionnalite, note_globale, ...}})
        - (NPSFeedback {{feedback_id, nps_score, categorie, profil_client, ...}})
        - (ServiceFeedback {{feedback_id, motif_contact, canal, temps_resolution, note_globale, ...}})
        - (SubscriptionFeedback {{feedback_id, type_contrat, canal, note_globale, ...}})
        - (Claim {{sinistre_id, type_sinistre, montant_reclame, montant_rembourse, statut, departement, ...}})
        - (Ticket {{ticket_id, resume, description, creation_date, departement}})
        - (Department {{name}})

        Relations principales:
        - Client-[:HAS_AGENCY_FEEDBACK]->AgencyFeedback
        - Client-[:HAS_APP_FEEDBACK]->AppFeedback
        - Client-[:HAS_NPS_FEEDBACK]->NPSFeedback
        - Client-[:HAS_SERVICE_FEEDBACK]->ServiceFeedback
        - Client-[:HAS_SUBSCRIPTION_FEEDBACK]->SubscriptionFeedback
        - Client-[:HAS_CLAIM]->Claim
        - Claim-[:HANDLED_BY]->Department
        - Ticket-[:BELONGS_TO]->Department

        Règles essentielles:
        1. Utilise uniquement l'outil `read_neo4j_cypher` du serveur MCP pour exécuter des requêtes Cypher.
        2. Les requêtes doivent être strictement en lecture (MATCH/RETURN, éventuellement CALL ... YIELD). Aucune écriture.
        3. N'ajoute pas de clause LIMIT: la plateforme gère le volume de données et doit pouvoir accéder à toutes les lignes pertinentes.
        4. Offre une réponse synthétique en français basée UNIQUEMENT sur les résultats retournés.
        5. Fourni l'objet `GraphAgentOutput` avec:
           - `answer`: résumé clair de l'insight.
           - `cypher`: la requête exécutée exactement telle qu'elle a été lancée.
        6. Retourne toujours les entités pertinentes avec leurs identifiants (ex: `t.ticket_id`, `t.creation_date`, `t.departement`) et évite d'ajouter des clauses LIMIT: la plateforme doit pouvoir afficher l'intégralité des lignes accessibles.
        """
    )

    def __init__(self) -> None:
        self._spec = self._resolve_spec()
        self._provider, self._model_name = self._build_provider()

    def run(self, prompt: str) -> Neo4jGraphResult:
        if not prompt.strip():
            raise Neo4jGraphError("La question utilisateur est vide.")

        agent_output = self._invoke_agent(prompt)
        cypher = agent_output.cypher.strip()
        if not cypher:
            raise Neo4jGraphError("Le modèle n'a pas fourni de requête Cypher.")

        sanitized_cypher = self._normalize_date_literals(cypher)
        if sanitized_cypher != cypher:
            log.debug("Normalisation des dates détectée dans la requête Cypher.")

        sanitized_no_limit = self._strip_limit_clauses(sanitized_cypher)
        if sanitized_no_limit != sanitized_cypher:
            log.debug("Suppression des clauses LIMIT détectée dans la requête Cypher.")
        sanitized_cypher = sanitized_no_limit

        client = Neo4jClient(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database or None,
            max_rows=0,
        )
        evidence_result: Optional[Neo4jResult] = None
        try:
            result = client.run_read(sanitized_cypher, limit=None)
            evidence_result = self._derive_detail_result(client, sanitized_cypher)
        except Neo4jClientError as exc:
            raise Neo4jGraphError(f"Échec de l'exécution Cypher: {exc}") from exc
        finally:
            client.close()

        snippet = " ".join(sanitized_cypher.split())
        if len(snippet) > 160:
            snippet = f"{snippet[:157]}..."
        log.info("Neo4j graph executed: rows=%d query=\"%s\"", result.row_count, snippet)

        harmonized_answer = self._harmonize_answer(
            question=prompt,
            original_answer=agent_output.answer.strip(),
            cypher=cypher,
            sanitized_cypher=sanitized_cypher,
            result=result,
            model_name=self._model_name,
            provider=self._provider,
        )

        display = evidence_result or result

        return Neo4jGraphResult(
            answer=harmonized_answer,
            cypher=sanitized_cypher,
            columns=display.columns,
            rows=display.rows,
            row_count=len(display.rows),
            model=self._model_name,
        )

    def _invoke_agent(self, prompt: str) -> GraphAgentOutput:
        limit = settings.neo4j_result_limit
        instructions = self._INSTRUCTIONS.format(limit=limit)
        server = MCPServerStdio(
            self._spec.command,
            self._spec.args,
            env=self._server_env(),
            tool_prefix=self._spec.name,
            timeout=30,
            read_timeout=300,
        )
        model = OpenAIChatModel(model_name=self._model_name, provider=self._provider)
        agent = Agent(
            model,
            name="neo4j-graph",
            instructions=instructions,
            output_type=GraphAgentOutput,
            toolsets=[server],
        )

        async def runner() -> GraphAgentOutput:
            try:
                async with agent:
                    result = await agent.run(prompt)
            except UnexpectedModelBehavior as exc:
                log.exception("Réponse LLM incompatible pour Neo4j")
                raise Neo4jGraphError(f"Réponse LLM incompatible: {exc}") from exc
            except Exception as exc:  # pragma: no cover - dépendances externes
                log.exception("Échec du run agent Neo4j")
                raise Neo4jGraphError(str(exc)) from exc
            return result.output

        return asyncio.run(runner())

    def _server_env(self) -> Dict[str, str]:
        env: Dict[str, str | None] = dict(self._spec.env or {})
        env.update(
            {
                "NEO4J_URI": settings.neo4j_uri,
                "NEO4J_USERNAME": settings.neo4j_username,
                "NEO4J_PASSWORD": settings.neo4j_password,
                "NEO4J_DATABASE": settings.neo4j_database,
            }
        )
        return {k: str(v) for k, v in env.items() if v not in {None, ""}}

    @staticmethod
    def _resolve_spec() -> MCPServerSpec:
        manager = MCPManager()
        for spec in manager.list_servers():
            if spec.name in {"neo4j", "mcp-neo4j-cypher"}:
                return spec
        raise Neo4jGraphError(
            "Serveur MCP 'neo4j' introuvable. Vérifiez MCP_CONFIG_PATH ou MCP_SERVERS_JSON."
        )

    def _build_provider(self) -> tuple[OpenAIProvider, str]:
        if settings.llm_mode not in {"local", "api"}:
            raise Neo4jGraphError("LLM_MODE doit valoir 'local' ou 'api'.")

        if settings.llm_mode == "local":
            base_url = (settings.vllm_base_url or "").rstrip("/")
            model_name = settings.z_local_model
            api_key: Optional[str] = None
        else:
            base_url = (settings.openai_base_url or "").rstrip("/")
            model_name = settings.llm_model
            api_key = settings.openai_api_key

        if not base_url or not model_name:
            raise Neo4jGraphError("Configuration LLM incomplète pour le mode Neo4j.")

        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
        return provider, str(model_name)

    @classmethod
    def _normalize_date_literals(cls, cypher: str) -> str:
        if not cypher:
            return cypher

        date_fields = Neo4jIngestionService.date_field_names()
        updated = cypher
        for field in date_fields:
            pattern = re.compile(
                rf"(?P<lhs>(?:\b[\w`]+\.)?`?{re.escape(field)}`?\b\s*(?:=|<>|!=|<=|>=|<|>|IN)\s*)(?P<rhs>\[[^\]]*\]|'[^']*')",
                flags=re.IGNORECASE,
            )

            def repl(match: re.Match[str]) -> str:
                lhs = match.group("lhs")
                rhs = match.group("rhs")
                normalized_rhs = cls._normalize_date_rhs(rhs)
                return f"{lhs}{normalized_rhs}"

            updated = pattern.sub(repl, updated)
        return updated

    @staticmethod
    def _normalize_date_rhs(raw_rhs: str) -> str:
        stripped = raw_rhs.strip()
        if not stripped:
            return raw_rhs

        prefix = raw_rhs[: len(raw_rhs) - len(raw_rhs.lstrip())]
        suffix = raw_rhs[len(raw_rhs.rstrip()) :]

        if stripped.startswith("[") and stripped.endswith("]"):
            inner = stripped[1:-1]

            def wrap_list_literal(match: re.Match[str]) -> str:
                literal = match.group(0)
                return Neo4jGraphService._wrap_date_literal(literal)

            transformed_inner = re.sub(r"'[^']*'", wrap_list_literal, inner)
            if transformed_inner == inner:
                return raw_rhs
            return f"{prefix}[{transformed_inner}]{suffix}"

        normalized = Neo4jGraphService._wrap_date_literal(stripped)
        if normalized == stripped:
            return raw_rhs
        return f"{prefix}{normalized}{suffix}"

    @staticmethod
    def _wrap_date_literal(literal: str) -> str:
        trimmed = literal.strip()
        lower = trimmed.lower()
        if lower.startswith("date(") or lower.startswith("datetime("):
            return literal
        if len(trimmed) >= 2 and trimmed[0] == trimmed[-1] == "'":
            value = trimmed[1:-1]
            if _ISO_DATE_RE.match(value):
                return f"date('{value}')"
            if _ISO_DATETIME_RE.match(value):
                return f"date('{value[:10]}')"
        return literal

    @staticmethod
    def _strip_limit_clauses(cypher: str) -> str:
        if not cypher:
            return cypher
        stripped = cypher
        pattern = re.compile(r"\s+LIMIT\s+\S+\s*$", flags=re.IGNORECASE)
        prev = None
        while stripped != prev:
            prev = stripped
            stripped = pattern.sub("", stripped)
        return stripped

    @classmethod
    def _derive_detail_result(
        cls,
        client: Neo4jClient,
        cypher: str,
    ) -> Optional[Neo4jResult]:
        detail_query = cls._derive_detail_query(cypher)
        if not detail_query:
            return None
        try:
            detail = client.run_read(detail_query, limit=None)
        except Neo4jClientError:
            log.warning("Échec de la requête de détails Neo4j", exc_info=True)
            return None
        return cls._prepare_evidence_result(detail)

    @classmethod
    def _derive_detail_query(cls, cypher: str) -> Optional[str]:
        s = cypher.strip()
        if not s:
            return None
        if not re.search(r"\breturn\b", s, re.IGNORECASE):
            return None

        has_aggregate = re.search(r"\b(count|avg|sum|min|max|collect)\s*\(", s, re.IGNORECASE)
        if not has_aggregate:
            return None

        parts = re.split(r"\breturn\b", s, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            return None
        prefix = parts[0].strip()
        if not prefix:
            return None
        detail_query = f"{prefix} RETURN *"
        return cls._strip_limit_clauses(detail_query)

    @staticmethod
    def _prepare_evidence_result(detail: Neo4jResult) -> Optional[Neo4jResult]:
        if not detail.rows:
            return None

        ordered_keys: list[str] = []
        shaped_rows: list[Dict[str, Any]] = []
        for row in detail.rows:
            shaped: Dict[str, Any] = {}
            for key, value in row.items():
                if isinstance(value, dict):
                    for nested_key, nested_value in value.items():
                        if nested_key not in ordered_keys:
                            ordered_keys.append(nested_key)
                        shaped.setdefault(nested_key, nested_value)
                else:
                    if key not in ordered_keys:
                        ordered_keys.append(key)
                    shaped.setdefault(key, value)
            shaped_rows.append(shaped)

        if not ordered_keys:
            ordered_keys = list(detail.columns)
        else:
            preferred = [
                "ticket_id",
                "feedback_id",
                "sinistre_id",
                "client_id",
                "creation_date",
                "date_feedback",
                "last_seen",
                "departement",
                "source",
            ]
            prioritized = [key for key in preferred if key in ordered_keys]
            others = [key for key in ordered_keys if key not in preferred]
            ordered_keys = prioritized + others

        return Neo4jResult(
            columns=ordered_keys,
            rows=shaped_rows,
            row_count=len(shaped_rows),
        )

    @staticmethod
    def _harmonize_answer(
        *,
        question: str,
        original_answer: str,
        cypher: str,
        sanitized_cypher: str,
        result: Neo4jResult,
        model_name: str,
        provider: OpenAIProvider,
    ) -> str:
        if sanitized_cypher == cypher:
            return original_answer

        regenerated = Neo4jGraphService._regenerate_answer(
            question=question,
            sanitized_cypher=sanitized_cypher,
            result=result,
            model_name=model_name,
            provider=provider,
        )
        if regenerated:
            log.debug("Réponse recalculée via le modèle après normalisation de la requête.")
            return regenerated
        return original_answer

    @staticmethod
    def _regenerate_answer(
        *,
        question: str,
        sanitized_cypher: str,
        result: Neo4jResult,
        model_name: str,
        provider: OpenAIProvider,
    ) -> str:
        snapshot = Neo4jGraphService._result_snapshot(result)
        if snapshot is None:
            return ""

        instructions = textwrap.dedent(
            f"""
            Tu es un assistant Neo4j. Ne lance aucun outil.
            Utilise les informations suivantes pour répondre en français à la question utilisateur.

            Question: {question}
            Requête exécutée:
            {sanitized_cypher}

            Résultats (colonnes, lignes limitées):
            {snapshot}
            """
        ).strip()

        model = OpenAIChatModel(model_name=model_name, provider=provider)
        agent = Agent(
            model,
            name="neo4j-graph-rewrite",
            instructions=instructions,
            output_type=GraphAnswerRewrite,
        )

        async def runner() -> str:
            async with agent:
                result_obj = await agent.run("Fournis la réponse finale en français.")
            return result_obj.output.answer.strip()

        try:
            return asyncio.run(runner())
        except Exception:  # pragma: no cover - dépendances externes
            log.exception("Impossible de recalculer la réponse Neo4j après normalisation.")
            return ""

    @staticmethod
    def _result_snapshot(result: Neo4jResult, *, max_rows: int = 20) -> Optional[str]:
        rows = result.rows or []
        columns = result.columns or []
        if not columns:
            return None
        preview = rows[:max_rows]
        payload = {
            "columns": columns,
            "row_count": result.row_count,
            "rows": preview,
            "truncated": len(rows) > len(preview),
        }
        try:
            return json.dumps(payload, ensure_ascii=False)
        except Exception:
            log.exception("Échec de la sérialisation des résultats Neo4j.")
            return None
