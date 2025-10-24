from __future__ import annotations

import asyncio
import logging
import textwrap
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
from ..integrations.neo4j_client import Neo4jClient, Neo4jClientError


log = logging.getLogger("insight.services.neo4j_graph")


class Neo4jGraphError(RuntimeError):
    """Raised when graph reasoning fails."""


class GraphAgentOutput(BaseModel):
    answer: str
    cypher: str


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
        3. Limite la taille des résultats avec LIMIT {limit} si la requête peut retourner beaucoup de lignes.
        4. Offre une réponse synthétique en français basée UNIQUEMENT sur les résultats retournés.
        5. Fourni l'objet `GraphAgentOutput` avec:
           - `answer`: résumé clair de l'insight.
           - `cypher`: la requête exécutée exactement telle qu'elle a été lancée.
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

        client = Neo4jClient(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            database=settings.neo4j_database or None,
            max_rows=settings.neo4j_result_limit,
        )
        try:
            result = client.run_read(cypher, limit=settings.neo4j_result_limit)
        except Neo4jClientError as exc:
            raise Neo4jGraphError(f"Échec de l'exécution Cypher: {exc}") from exc
        finally:
            client.close()

        snippet = " ".join(cypher.split())
        if len(snippet) > 160:
            snippet = f"{snippet[:157]}..."
        log.info("Neo4j graph executed: rows=%d query=\"%s\"", result.row_count, snippet)

        return Neo4jGraphResult(
            answer=agent_output.answer.strip(),
            cypher=cypher,
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
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
