from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

import sqlglot
from sqlglot import exp
from sqlalchemy import text

from ...core.config import settings
from ...core.database import engine, discover_rag_tables
from .common import quote_identifier, resolve_text_column, vector_literal
from .encoder import EmbeddingBackend


log = logging.getLogger("insight.services.rag")

DISTANCE_OPERATORS = {
    "cosine": "<=>",
    "l2": "<->",
    "ip": "<#>",
}


@dataclass
class RagSnippet:
    id: Any
    text: str
    distance: float
    score: float
    record: Dict[str, Any]


@dataclass
class RagPayload:
    table: str
    stem: str
    where_sql: str
    snippets: List[RagSnippet]
    distance_operator: str


class RAGRetriever:
    """Compute question embedding and retrieve similar rows constrained by SQL filters."""

    def __init__(self, encoder: EmbeddingBackend | None = None):
        self.encoder = encoder or EmbeddingBackend()
        self._table_map: dict[str, str] | None = None

    def refresh_tables(self) -> None:
        self._table_map = discover_rag_tables()

    def _tables(self) -> dict[str, str]:
        if self._table_map is None:
            self.refresh_tables()
        return self._table_map or {}

    def retrieve(self, *, question: str, final_sql: str) -> RagPayload | None:
        question_clean = (question or "").strip()
        if not question_clean:
            log.info("RAG skipped: empty question.")
            return None
        mapping = self._tables()
        if not mapping:
            log.info("RAG skipped: no vector-enabled tables detected.")
            return None
        inverse = {stem: table for table, stem in mapping.items()}
        try:
            parsed = sqlglot.parse_one(final_sql, read="postgres")
        except Exception as exc:
            log.warning("RAG skipped: failed to parse final SQL (%s)", exc)
            return None

        table_info = self._extract_primary_table(parsed, inverse)
        if table_info is None:
            return None
        actual_table, stem, alias = table_info
        where_exp = parsed.args.get("where")
        if where_exp is None:
            log.info("RAG skipped: final SQL has no WHERE clause (table=%s).", actual_table)
            return None
        where_sql = self._rebind_where(where_exp.copy(), alias, stem)
        if not where_sql.strip():
            log.info("RAG skipped: derived WHERE clause empty (table=%s).", actual_table)
            return None

        vector = self.encoder.encode_one(question_clean)
        if not vector:
            log.info("RAG skipped: question embedding empty.")
            return None

        snippets = self._search(actual_table, stem, where_sql, vector)
        if not snippets:
            log.info("RAG: no snippets under threshold for %s.", actual_table)
            return None
        return RagPayload(
            table=actual_table,
            stem=stem,
            where_sql=where_sql,
            snippets=snippets,
            distance_operator=DISTANCE_OPERATORS[settings.rag_distance],
        )

    def _extract_primary_table(
        self,
        parsed: exp.Expression,
        inverse: Dict[str, str],
    ) -> tuple[str, str, str] | None:
        tables = list(parsed.find_all(exp.Table))
        for table in tables:
            stem = table.name
            if stem not in inverse:
                continue
            actual = inverse[stem]
            alias = table.alias or stem
            return actual, stem, alias
        log.info("RAG skipped: no matching table found in final SQL (tables=%s).", [t.name for t in tables])
        return None

    def _rebind_where(self, where_exp: exp.Expression, alias: str, stem: str) -> str:
        target_alias = "rag"
        identifier = exp.to_identifier(target_alias)
        for column in where_exp.find_all(exp.Column):
            table_name = column.table
            if table_name is None or table_name == alias or table_name == stem:
                column.set("table", identifier.copy())
        return where_exp.sql(dialect="postgres")

    def _search(
        self,
        actual_table: str,
        stem: str,
        where_sql: str,
        vector: List[float],
    ) -> List[RagSnippet]:
        distance_op = DISTANCE_OPERATORS[settings.rag_distance]
        table_sql = quote_identifier(actual_table)
        text_column = resolve_text_column(actual_table, stem)
        column_sql = quote_identifier(text_column)
        query = text(
            f"""
            SELECT
                rag.id,
                {column_sql} AS text,
                rag.embedding {distance_op} :vector::vector AS distance,
                (to_jsonb(rag) - 'embedding') AS record
            FROM {table_sql} AS rag
            WHERE rag.embedding IS NOT NULL
              AND ({where_sql})
            ORDER BY distance
            LIMIT :limit
            """
        )
        params = {
            "vector": vector_literal(vector),
            "limit": settings.rag_top_k,
        }
        rows = []
        with engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        if not rows:
            return []
        results: list[RagSnippet] = []
        threshold = settings.rag_similarity_threshold
        for row in rows:
            distance = float(row.distance)
            if not self._passes_threshold(distance, threshold):
                continue
            score = self._similarity(distance)
            record = row.record if isinstance(row.record, dict) else {}
            results.append(
                RagSnippet(
                    id=row.id,
                    text=row.text,
                    distance=distance,
                    score=score,
                    record=record,
                )
            )
        return results

    def _passes_threshold(self, distance: float, threshold: float) -> bool:
        mode = settings.rag_distance
        if mode == "ip":
            return (-distance) >= threshold
        return distance <= threshold

    def _similarity(self, distance: float) -> float:
        mode = settings.rag_distance
        if mode == "cosine":
            return max(0.0, 1.0 - distance)
        if mode == "ip":
            return -distance
        # l2
        return max(0.0, settings.rag_similarity_threshold - distance)
