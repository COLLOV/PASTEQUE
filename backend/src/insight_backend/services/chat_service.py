import logging
import re
from pathlib import Path
from typing import Protocol, Callable, Dict, Any, Iterable

from ..schemas.chat import ChatRequest, ChatResponse, ChatMessage
from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..repositories.data_repository import DataRepository
from .nl2sql_service import NL2SQLService
from .neo4j_graph_service import Neo4jGraphError, Neo4jGraphService


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
        events: Callable[[str, Dict[str, Any]], None] | None = None,
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
                        "rows": rows if isinstance(rows, list) else [],
                        "row_count": len(rows) if isinstance(rows, list) else 0,
                    }
                    try:
                        events("rows", snapshot)
                    except Exception:  # pragma: no cover - defensive
                        pass

                # Emit evidence contract + dataset (generic) so the front can open the panel
                self._emit_evidence(
                    events=events,
                    client=client,
                    label_hint=sql,
                    base_sql=sql,
                    fallback_columns=columns,
                    fallback_rows=rows,
                )

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

        meta = payload.metadata or {}
        neo4j_flag = meta.get("neo4j") if isinstance(meta, dict) else None
        neo4j_enabled = bool(neo4j_flag)

        if payload.messages and neo4j_enabled:
            last = payload.messages[-1]
            if last.role == "user":
                raw_question, contextual_question = self._prepare_nl2sql_question(payload.messages)
                graph_service = Neo4jGraphService()
                log.info(
                    "Neo4j graph question prepared: raw=\"%s\" enriched_preview=\"%s\"",
                    _preview_text(raw_question, limit=200),
                    _preview_text(contextual_question, limit=200),
                )
                try:
                    result = graph_service.run(contextual_question or raw_question)
                except Neo4jGraphError as exc:
                    message = f"Erreur Neo4j: {exc}"
                    log.info("Neo4j graph generation failed: %s", exc)
                    return self._log_completion(
                        ChatResponse(reply=message, metadata={"provider": "neo4j-error"}),
                        context="completion done (neo4j-error)",
                    )

                if events:
                    try:
                        events(
                            "meta",
                            {
                                "provider": "neo4j-graph",
                                "model": result.model,
                            },
                        )
                        events("cypher", {"query": result.cypher})
                    except Exception:
                        log.warning("Failed to emit Neo4j meta/cypher events", exc_info=True)
                    if result.columns and result.rows:
                        spec = self._build_evidence_spec(result.columns, label_hint=result.cypher)
                        try:
                            events("meta", {"evidence_spec": spec})
                            events(
                                "rows",
                                {
                                    "purpose": "evidence",
                                    "columns": result.columns,
                                    "rows": result.rows,
                                    "row_count": result.row_count,
                                },
                            )
                        except Exception:
                            log.warning("Failed to emit Neo4j evidence events", exc_info=True)

                response = ChatResponse(
                    reply=result.answer or "(Aucune réponse)",
                    metadata={"provider": "neo4j", "cypher": result.cypher},
                )
                return self._log_completion(response, context="completion done (neo4j)")

        # NL→SQL (optional): per-request override via payload.metadata.nl2sql,
        # falling back to env `NL2SQL_ENABLED` when not specified.
        nl2sql_flag = meta.get("nl2sql") if isinstance(meta, dict) else None
        nl2sql_enabled = bool(nl2sql_flag) if (nl2sql_flag is not None) else settings.nl2sql_enabled

        if payload.messages and nl2sql_enabled:
            last = payload.messages[-1]
            if last.role == "user":
                raw_question, contextual_question = self._prepare_nl2sql_question(payload.messages)
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
                log.info(
                    "NL2SQL question prepared: raw=\"%s\" enriched_preview=\"%s\"",
                    _preview_text(raw_question, limit=200),
                    _preview_text(contextual_question, limit=200),
                )
                client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)

                # Multi-step planning if enabled
                if settings.nl2sql_plan_enabled:
                    try:
                        plan = nl2sql.plan(question=contextual_question, schema=schema, max_steps=settings.nl2sql_plan_max_steps)
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
                    last_columns: list[Any] = []
                    last_rows: list[Any] = []
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
                            except Exception:
                                log.warning("Failed to emit sql event (plan step)", exc_info=True)
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
                                        "rows": rows,
                                        "row_count": len(rows),
                                    },
                                )
                            except Exception:
                                log.warning("Failed to emit rows event (plan step)", exc_info=True)
                        evidence.append({
                            "purpose": purpose,
                            "sql": sql,
                            "columns": columns,
                            "rows": rows,
                        })
                        # retain last non-empty dataset as evidence surface
                        if columns and rows:
                            last_columns = columns
                            last_rows = rows
                    try:
                        answer = nl2sql.synthesize(question=contextual_question, evidence=evidence).strip()
                        reply_text = answer or "Je n'ai pas pu formuler de réponse à partir des résultats."
                        # Provide an evidence_spec + evidence rows via helper
                        target_sql = (
                            plan[-1]["sql"] if plan and isinstance(plan[-1], dict) and plan[-1].get("sql") else None
                        )
                        self._emit_evidence(
                            events=events,
                            client=client,
                            label_hint=raw_question,
                            base_sql=target_sql if isinstance(target_sql, str) else None,
                            fallback_columns=last_columns,
                            fallback_rows=last_rows,
                        )
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
                        sql = nl2sql.generate(question=contextual_question, schema=schema)
                        log.info("MindsDB SQL (single-shot): %s", _preview_text(str(sql), limit=200))
                        if events:
                            try:
                                events("sql", {"sql": sql})
                            except Exception:
                                log.warning("Failed to emit sql event (single-shot)", exc_info=True)
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
                                    "rows": rows,
                                    "row_count": len(rows),
                                },
                            )
                        except Exception:
                            log.warning("Failed to emit rows event", exc_info=True)
                    # Emit evidence contract + dataset for the front panel (consolidated)
                    self._emit_evidence(
                        events=events,
                        client=client,
                        label_hint=raw_question,
                        base_sql=sql,
                        fallback_columns=columns,
                        fallback_rows=rows,
                    )
                    evidence = [{
                        "purpose": "answer",
                        "sql": sql,
                        "columns": columns,
                        "rows": rows,
                    }]
                    try:
                        answer = nl2sql.synthesize(question=contextual_question, evidence=evidence).strip()
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

    # ----------------------
    # Helpers
    # ----------------------
    def _prepare_nl2sql_question(self, messages: list[ChatMessage]) -> tuple[str, str]:
        """Return the raw user question plus a context-enriched variant for NL→SQL."""
        if not messages:
            return "", ""
        last = messages[-1]
        question = last.content.strip()
        if not question:
            return "", ""

        history: list[str] = []
        for msg in messages[:-1]:
            text = msg.content.strip()
            if not text:
                continue
            if msg.role == "system":
                continue
            speaker = "User" if msg.role == "user" else "Assistant"
            history.append(f"{speaker}: {text}")
        if not history:
            return question, question
        context = "\n".join(history[-8:])
        enriched = (
            "Conversation history (keep implicit references consistent):\n"
            f"{context}\n"
            f"Current user question: {question}"
        )
        return question, enriched

    def _build_evidence_spec(self, columns: list[Any], *, label_hint: str | None = None) -> dict[str, Any]:
        """Build a generic evidence spec from available columns.

        Not a UI heuristic: this is an explicit contract so the front can render
        a generic panel for any entity. We pick commonly used field names when present.
        """
        cols_lc = [str(c) for c in columns]
        cols_set = {c.casefold() for c in cols_lc}
        def pick(*candidates: str) -> str | None:
            for c in candidates:
                if c.casefold() in cols_set:
                    return c
            return None

        # Label guessing based on hint/columns (transparent; only used for labeling)
        label = "Éléments"
        text = (label_hint or "").casefold()
        if "ticket" in text or any("ticket" in c for c in cols_set):
            label = "Tickets"
        elif "feedback" in text or any("feedback" in c for c in cols_set):
            label = "Feedback"

        pk = pick("ticket_id", "feedback_id", "id", "pk") or (cols_lc[0] if cols_lc else "id")
        created_at = pick("created_at", "createdAt", "date", "timestamp", "createdon", "created")
        status = pick("status", "state")
        title = pick("title", "subject", "name")

        spec: dict[str, Any] = {
            "entity_label": label,
            "pk": pk,
            "display": {
                **({"title": title} if title else {}),
                **({"status": status} if status else {}),
                **({"created_at": created_at} if created_at else {}),
            },
            "columns": cols_lc,
            "limit": settings.evidence_limit_default,
        }
        return spec

    def _normalize_result(self, data: Any) -> tuple[list[Any], list[Any]]:
        """Extract columns and rows from MindsDB result payloads."""
        rows: list[Any] = []
        columns: list[Any] = []
        if isinstance(data, dict):
            if data.get("type") == "table":
                columns = data.get("column_names") or []
                rows = data.get("data") or []
            if not rows:
                rows = data.get("result", {}).get("rows") or data.get("rows") or rows
            if not columns:
                columns = data.get("result", {}).get("columns") or data.get("columns") or columns
        return columns or [], rows or []

    def _derive_evidence_sql(self, sql: str, *, limit: int | None = None) -> str | None:
        """Attempt to derive a detail-level SELECT from an aggregate SQL.

        This is a best-effort utility and logs on failure without masking errors.
        Strategy: extract FROM ... [WHERE ...] then build SELECT * with same filters.
        """
        try:
            if limit is None:
                limit = settings.evidence_limit_default
            s = sql.strip()
            # Quick bail if looks like detail already (select * or explicit columns without COUNT/AVG/etc.)
            if re.search(r"\bselect\s+\*", s, re.I):
                return s if re.search(r"\blimit\b", s, re.I) else f"{s} LIMIT {limit}"
            if not re.search(r"\bcount\s*\(|\bavg\s*\(|\bmin\s*\(|\bmax\s*\(|\bsum\s*\(", s, re.I):
                # Non-aggregate: just cap the limit
                return s if re.search(r"\blimit\b", s, re.I) else f"{s} LIMIT {limit}"
            # Extract FROM ... tail
            m_from = re.search(r"\bfrom\b\s+(.*)$", s, re.I | re.S)
            if not m_from:
                return None
            tail = m_from.group(1)
            # Cut at ORDER BY / LIMIT / OFFSET
            tail = re.split(r"\border\s+by\b|\blimit\b|\boffset\b", tail, flags=re.I)[0].strip()
            # Extract WHERE if present
            where = None
            m_where = re.search(r"\bwhere\b\s+(.*)$", tail, re.I | re.S)
            if m_where:
                where = re.split(r"\bgroup\s+by\b|\border\s+by\b|\blimit\b|\boffset\b", m_where.group(1), flags=re.I)[0].strip()
                from_part = tail[: m_where.start()].strip()
            else:
                from_part = tail
            base = f"SELECT * FROM {from_part}"
            if where:
                base += f" WHERE {where}"
            base += f" LIMIT {limit}"
            # Ensure SELECT-only (no accidental DML)
            if not re.match(r"^\s*select\b", base, re.I):
                return None
            if re.search(r";|\b(insert|update|delete|alter|drop|create)\b", base, re.I):
                return None
            return base
        except Exception as e:  # pragma: no cover - defensive
            log.warning("_derive_evidence_sql failed", exc_info=True)
            return None

    def _emit_evidence(
        self,
        *,
        events: Callable[[str, Dict[str, Any]], None] | None,
        client: MindsDBClient,
        label_hint: str,
        base_sql: str | None = None,
        fallback_columns: list[Any] | None = None,
        fallback_rows: list[Any] | None = None,
    ) -> None:
        """Consolidated evidence emission.

        Emits:
          - optional "sql" event with purpose:"evidence" for the derived detail query
          - "meta" with evidence_spec
          - "rows" with purpose:"evidence"
        """
        if not events:
            return
        try:
            ev_cols: list[Any] = []
            ev_rows: list[Any] = []
            derived: str | None = None
            if base_sql:
                derived = self._derive_evidence_sql(base_sql)
            if derived:
                try:
                    events("sql", {"sql": derived, "purpose": "evidence"})
                except Exception:
                    log.warning("Failed to emit evidence SQL event", exc_info=True)
                ev = client.sql(derived)
                ev_cols, ev_rows = self._normalize_result(ev)
            else:
                if fallback_columns and fallback_rows:
                    ev_cols, ev_rows = fallback_columns, fallback_rows
            if ev_cols and ev_rows:
                spec = self._build_evidence_spec(ev_cols, label_hint=label_hint)
                events("meta", {"evidence_spec": spec})
                events(
                    "rows",
                    {
                        "purpose": "evidence",
                        "columns": ev_cols,
                        "rows": ev_rows,
                        "row_count": len(ev_rows),
                    },
                )
                log.info(
                    "Emitted evidence_spec: label=%s cols=%d rows=%d",
                    spec.get("entity_label"),
                    len(ev_cols),
                    len(ev_rows),
                )
        except Exception:
            # Defensive: do not break the main flow, but keep traceback
            log.warning("Failed to emit evidence (helper)", exc_info=True)
