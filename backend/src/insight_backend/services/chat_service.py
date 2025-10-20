import logging
from pathlib import Path
from typing import Protocol

from ..schemas.chat import ChatRequest, ChatResponse
from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..repositories.data_repository import DataRepository
from .nl2sql_service import NL2SQLService


log = logging.getLogger("insight.services.chat")


class ChatEngine(Protocol):
    def run(self, payload: ChatRequest) -> ChatResponse:  # type: ignore[valid-type]
        ...


class ChatService:
    """Orchestre les appels à un moteur de chat.

    Implémentation réelle à fournir ultérieurement.
    """

    def __init__(self, engine: ChatEngine):
        self.engine = engine

    def _llm_diag(self) -> str:
        if settings.llm_mode == "api":
            return (
                f"LLM(mode=api, base_url={settings.openai_base_url}, model={settings.llm_model})"
            )
        return (
            f"LLM(mode=local, base_url={settings.vllm_base_url}, model={settings.z_local_model})"
        )

    def completion(self, payload: ChatRequest) -> ChatResponse:  # type: ignore[valid-type]
        # Lightweight command passthrough for MindsDB SQL without changing the UI.
        # If the last user message starts with '/sql ', execute it against MindsDB and return the result.
        if payload.messages:
            last = payload.messages[-1]
            if last.role == "user" and last.content.strip().lower().startswith("/sql "):
                sql = last.content.strip()[5:]
                client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)
                data = client.sql(sql)
                # Normalize common MindsDB shapes
                rows = []
                columns = []
                if isinstance(data, dict):
                    # MindsDB table shape
                    if data.get("type") == "table":
                        columns = data.get("column_names") or []
                        rows = data.get("data") or []
                    # Alternate shapes
                    if not rows:
                        rows = data.get("result", {}).get("rows") or data.get("rows") or rows
                    if not columns:
                        columns = data.get("result", {}).get("columns") or data.get("columns") or columns

                if rows and columns:
                    header = " | ".join(str(c) for c in columns)
                    lines = [header, "-" * len(header)]
                    for r in rows[:50]:
                        if isinstance(r, dict):
                            line = " | ".join(str(r.get(c)) for c in columns)
                        else:
                            line = " | ".join(str(v) for v in r)
                        lines.append(line)
                    text = "\n".join(lines)
                else:
                    # Error forwarding
                    err = data.get("error_message") if isinstance(data, dict) else None
                    text = err or "(Aucune ligne)"
                return ChatResponse(reply=text, metadata={"provider": "mindsdb-sql"})

        # NL→SQL (optional, explicit opt-in via env)
        if payload.messages and settings.nl2sql_enabled:
            last = payload.messages[-1]
            if last.role == "user":
                # Build schema from local CSV headers
                repo = DataRepository(tables_dir=Path(settings.tables_dir))
                schema: dict[str, list[str]] = {}
                for name in repo.list_tables():
                    cols = [c for c, _ in repo.get_schema(name)]
                    schema[name] = cols
                nl2sql = NL2SQLService()
                log.info("NL2SQL question: %s", last.content.strip())
                client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)

                # Multi-step planning if enabled
                if settings.nl2sql_plan_enabled:
                    try:
                        plan = nl2sql.plan(question=last.content.strip(), schema=schema, max_steps=settings.nl2sql_plan_max_steps)
                        log.info("NL2SQL plan (%d steps)", len(plan))
                    except Exception as e:
                        log.error("NL2SQL plan failed: %s", e)
                        return ChatResponse(
                            reply=f"Échec du plan NL→SQL: {e}\n{self._llm_diag()}",
                            metadata={"provider": "nl2sql-plan"},
                        )
                    evidence: list[dict[str, object]] = []
                    for item in plan:
                        sql = item["sql"]
                        purpose = item.get("purpose", "")
                        log.info("MindsDB SQL (plan) [%s]: %s", purpose or "step", sql)
                        data = client.sql(sql)
                        # Normalize
                        rows: list = []
                        columns: list = []
                        if isinstance(data, dict):
                            if data.get("type") == "table":
                                columns = data.get("column_names") or []
                                rows = data.get("data") or []
                            if not rows:
                                rows = data.get("result", {}).get("rows") or data.get("rows") or rows
                            if not columns:
                                columns = data.get("result", {}).get("columns") or data.get("columns") or columns
                        evidence.append({
                            "purpose": purpose,
                            "sql": sql,
                            "columns": columns,
                            "rows": rows[: settings.nl2sql_max_rows],
                        })
                    try:
                        answer = nl2sql.synthesize(question=last.content.strip(), evidence=evidence)
                        queries_block = ["Requêtes exécutées via MindsDB:"]
                        for idx, item in enumerate(plan, start=1):
                            purpose = item.get("purpose", "").strip()
                            header = f"{idx}. {purpose}" if purpose else f"{idx}."
                            queries_block.append(f"{header}\n{item['sql']}")
                        reply_text = "\n\n".join(["\n".join(queries_block), f"Réponse:\n{answer}"])
                        return ChatResponse(reply=reply_text, metadata={"provider": "nl2sql-plan+mindsdb", "plan": plan})
                    except Exception as e:
                        log.error("NL2SQL synthesis failed: %s", e)
                        return ChatResponse(
                            reply=f"Échec de la synthèse: {e}\n{self._llm_diag()}",
                            metadata={"provider": "nl2sql-synth"},
                        )
                else:
                    # Single-shot NL→SQL with natural-language synthesis
                    try:
                        sql = nl2sql.generate(question=last.content.strip(), schema=schema)
                        log.info("MindsDB SQL (single-shot): %s", sql)
                    except Exception as e:
                        log.error("NL2SQL generation failed: %s", e)
                        return ChatResponse(
                            reply=f"Échec de la génération SQL: {e}\n{self._llm_diag()}",
                            metadata={"provider": "nl2sql"},
                        )
                    data = client.sql(sql)
                    # Normalize to columns/rows and synthesize final answer
                    rows = []
                    columns = []
                    if isinstance(data, dict):
                        if data.get("type") == "table":
                            columns = data.get("column_names") or []
                            rows = data.get("data") or []
                        if not rows:
                            rows = data.get("result", {}).get("rows") or data.get("rows") or rows
                        if not columns:
                            columns = data.get("result", {}).get("columns") or data.get("columns") or columns
                    evidence = [{
                        "purpose": "answer",
                        "sql": sql,
                        "columns": columns,
                        "rows": rows[: settings.nl2sql_max_rows],
                    }]
                    try:
                        answer = nl2sql.synthesize(question=last.content.strip(), evidence=evidence)
                        queries_block = ["Requêtes exécutées via MindsDB:", f"1.\n{sql}"]
                        reply_text = "\n\n".join(["\n".join(queries_block), f"Réponse:\n{answer}"])
                        return ChatResponse(reply=reply_text, metadata={"provider": "nl2sql+mindsdb", "sql": sql})
                    except Exception as e:
                        # fallback to simple textual rendering (no hidden failures)
                        log.error("NL2SQL synthesis fallback after error: %s", e)
                        if rows and columns:
                            header = " | ".join(str(c) for c in columns)
                            lines = [f"SQL: {sql}", header, "-" * len(header)]
                            for r in rows[:50]:
                                if isinstance(r, dict):
                                    line = " | ".join(str(r.get(c)) for c in columns)
                                else:
                                    line = " | ".join(str(v) for v in r)
                                lines.append(line)
                            text = "\n".join(lines)
                        else:
                            err = data.get("error_message") if isinstance(data, dict) else None
                            text = f"SQL: {sql}\n" + (err or "(Aucune ligne)")
                        return ChatResponse(reply=text, metadata={"provider": "nl2sql-synth-fallback", "error": str(e), "sql": sql})

        return self.engine.run(payload)
