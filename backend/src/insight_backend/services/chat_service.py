import logging
from pathlib import Path
from typing import Protocol, Callable, Optional, Dict, Any, Iterable

from ..schemas.chat import ChatRequest, ChatResponse
from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..repositories.data_repository import DataRepository
from .nl2sql_service import NL2SQLService


log = logging.getLogger("insight.services.chat")


def _preview_text(text: str, *, limit: int = 160) -> str:
    """Return a single-line preview capped at ``limit`` characters."""
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    cutoff = max(limit - 3, 1)
    return f"{compact[:cutoff]}..."


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

    def _log_completion(self, response: ChatResponse, *, context: str) -> ChatResponse:
        provider = (response.metadata or {}).get("provider", "-")
        log.info(
            "ChatService.%s: provider=%s reply_preview=\"%s\"",
            context,
            provider,
            _preview_text(response.reply),
        )
        return response

    def completion(
        self,
        payload: ChatRequest,
        *,
        events: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        allowed_tables: Iterable[str] | None = None,
    ) -> ChatResponse:  # type: ignore[valid-type]
        metadata_keys = list((payload.metadata or {}).keys())
        message_count = len(payload.messages)
        if payload.messages:
            last = payload.messages[-1]
            log.info(
                "ChatService.completion start: count=%d last_role=%s preview=\"%s\" mode=%s metadata_keys=%s",
                message_count,
                last.role,
                _preview_text(last.content),
                settings.llm_mode,
                metadata_keys,
            )
        else:
            log.info(
                "ChatService.completion start: count=0 mode=%s metadata_keys=%s",
                settings.llm_mode,
                metadata_keys,
            )
        # Lightweight command passthrough for MindsDB SQL without changing the UI.
        # If the last user message starts with '/sql ', execute it against MindsDB and return the result.
        if payload.messages:
            last = payload.messages[-1]
            if last.role == "user" and last.content.strip().casefold().startswith("/sql "):
                sql = last.content.strip()[5:]
                log.info(
                    "ChatService.mindsdb passthrough: sql_preview=\"%s\"",
                    _preview_text(sql, limit=200),
                )
                if events:
                    try:
                        events("sql", {"sql": sql})
                    except Exception:  # pragma: no cover - defensive
                        pass
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

                if events:
                    snapshot = {
                        "columns": columns,
                        "rows": (rows[: settings.nl2sql_max_rows] if isinstance(rows, list) else []),
                        "row_count": len(rows) if isinstance(rows, list) else 0,
                    }
                    try:
                        events("rows", snapshot)
                    except Exception:  # pragma: no cover - defensive
                        pass

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
                log.info(
                    "ChatService.mindsdb passthrough response: columns=%d rows=%d",
                    len(columns),
                    len(rows),
                )
                return self._log_completion(
                    ChatResponse(reply=text, metadata={"provider": "mindsdb-sql"}),
                    context="completion done (mindsdb-sql)",
                )

        # NL→SQL (optional): per-request override via payload.metadata.nl2sql,
        # falling back to env `NL2SQL_ENABLED` when not specified.
        meta = payload.metadata or {}
        nl2sql_flag = meta.get("nl2sql") if isinstance(meta, dict) else None
        nl2sql_enabled = bool(nl2sql_flag) if (nl2sql_flag is not None) else settings.nl2sql_enabled

        if payload.messages and nl2sql_enabled:
            last = payload.messages[-1]
            if last.role == "user":
                # Build schema from local CSV headers
                repo = DataRepository(tables_dir=Path(settings.tables_dir))
                tables = repo.list_tables()
                allowed_lookup = {name.casefold() for name in allowed_tables} if allowed_tables is not None else None
                if allowed_lookup is not None:
                    tables = [name for name in tables if name.casefold() in allowed_lookup]
                if not tables:
                    message = (
                        "Aucune table n'est disponible pour vos requêtes. "
                        "Contactez un administrateur pour obtenir les accès nécessaires."
                    )
                    log.info("NL2SQL aborted: no tables available for user")
                    return self._log_completion(
                        ChatResponse(reply=message, metadata={"provider": "nl2sql-acl"}),
                        context="completion denied (no tables)",
                    )
                schema: dict[str, list[str]] = {}
                for name in tables:
                    cols = [c for c, _ in repo.get_schema(name)]
                    schema[name] = cols
                nl2sql = NL2SQLService()
                log.info("NL2SQL question: %s", _preview_text(last.content.strip(), limit=200))
                client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)

                # Multi-step planning if enabled
                if settings.nl2sql_plan_enabled:
                    try:
                        plan = nl2sql.plan(question=last.content.strip(), schema=schema, max_steps=settings.nl2sql_plan_max_steps)
                        log.info("NL2SQL plan (%d steps)", len(plan))
                        if events:
                            try:
                                events("plan", {"steps": plan})
                            except Exception:  # pragma: no cover
                                pass
                    except Exception as e:
                        log.error("NL2SQL plan failed: %s", e)
                        return self._log_completion(
                            ChatResponse(
                                reply=f"Échec du plan NL→SQL: {e}\n{self._llm_diag()}",
                                metadata={"provider": "nl2sql-plan"},
                            ),
                            context="completion done (nl2sql-plan-error)",
                        )
                    evidence: list[dict[str, object]] = []
                    for idx, item in enumerate(plan, start=1):
                        sql = item["sql"]
                        purpose = item.get("purpose", "")
                        log.info(
                            "MindsDB SQL (plan) [%s]: %s",
                            purpose or "step",
                            _preview_text(str(sql), limit=200),
                        )
                        if events:
                            try:
                                events("sql", {"sql": sql, "purpose": purpose, "step": idx})
                            except Exception:  # pragma: no cover
                                pass
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
                        if events:
                            try:
                                events(
                                    "rows",
                                    {
                                        "step": idx,
                                        "columns": columns,
                                        "rows": rows[: settings.nl2sql_max_rows],
                                        "row_count": len(rows),
                                    },
                                )
                            except Exception:  # pragma: no cover
                                pass
                        evidence.append({
                            "purpose": purpose,
                            "sql": sql,
                            "columns": columns,
                            "rows": rows[: settings.nl2sql_max_rows],
                        })
                    try:
                        answer = nl2sql.synthesize(question=last.content.strip(), evidence=evidence).strip()
                        reply_text = answer or "Je n'ai pas pu formuler de réponse à partir des résultats."
                        return self._log_completion(
                            ChatResponse(reply=reply_text, metadata={"provider": "nl2sql-plan+mindsdb", "plan": plan}),
                            context="completion done (nl2sql-plan)",
                        )
                    except Exception as e:
                        log.error("NL2SQL synthesis failed: %s", e)
                        return self._log_completion(
                            ChatResponse(
                                reply=f"Échec de la synthèse: {e}\n{self._llm_diag()}",
                                metadata={"provider": "nl2sql-synth"},
                            ),
                            context="completion done (nl2sql-synth-error)",
                        )
                else:
                    # Single-shot NL→SQL with natural-language synthesis
                    try:
                        sql = nl2sql.generate(question=last.content.strip(), schema=schema)
                        log.info("MindsDB SQL (single-shot): %s", _preview_text(str(sql), limit=200))
                        if events:
                            try:
                                events("sql", {"sql": sql})
                            except Exception:  # pragma: no cover
                                pass
                    except Exception as e:
                        log.error("NL2SQL generation failed: %s", e)
                        return self._log_completion(
                            ChatResponse(
                                reply=f"Échec de la génération SQL: {e}\n{self._llm_diag()}",
                                metadata={"provider": "nl2sql"},
                            ),
                            context="completion done (nl2sql-error)",
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
                    if events:
                        try:
                            events(
                                "rows",
                                {
                                    "columns": columns,
                                    "rows": rows[: settings.nl2sql_max_rows],
                                    "row_count": len(rows),
                                },
                            )
                        except Exception:  # pragma: no cover
                            pass
                    evidence = [{
                        "purpose": "answer",
                        "sql": sql,
                        "columns": columns,
                        "rows": rows[: settings.nl2sql_max_rows],
                    }]
                    try:
                        answer = nl2sql.synthesize(question=last.content.strip(), evidence=evidence).strip()
                        reply_text = answer or "Je n'ai pas pu formuler de réponse à partir des résultats."
                        return self._log_completion(
                            ChatResponse(reply=reply_text, metadata={"provider": "nl2sql+mindsdb", "sql": sql}),
                            context="completion done (nl2sql)",
                        )
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
                        return self._log_completion(
                            ChatResponse(
                                reply=text,
                                metadata={"provider": "nl2sql-synth-fallback", "error": str(e), "sql": sql},
                            ),
                            context="completion done (nl2sql-fallback)",
                        )
        response = self.engine.run(payload)
        return self._log_completion(response, context="completion done (engine)")
