from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence

from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..integrations.openai_client import OpenAIBackendError
from .mindsdb_embeddings import (
    EmbeddingConfig,
    EmbeddingTableConfig,
    build_embedding_client,
    load_embedding_config,
    normalise_embedding,
)


log = logging.getLogger("insight.services.retrieval")

_SNIPPET_LIMIT = 240


@dataclass(slots=True)
class SimilarRow:
    table: str
    score: float
    values: dict[str, str]
    focus: str
    source_column: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "score": round(self.score, 4),
            "focus": self.focus,
            "source_column": self.source_column,
            "values": self.values,
        }


class RetrievalService:
    """Compute question embeddings and surface the most similar rows from MindsDB."""

    def __init__(self, *, config_path: str | None = None):
        self._config_path = config_path or settings.mindsdb_embeddings_config_path
        self._config: EmbeddingConfig | None = None

    def retrieve(self, *, question: str, top_n: int | None = None) -> List[SimilarRow]:
        question = (question or "").strip()
        if not question:
            raise ValueError("Question must not be empty for retrieval.")

        top = top_n or settings.rag_top_n
        if top <= 0:
            raise ValueError("top_n must be > 0.")

        config = self._ensure_config()
        embedding_client, embedding_model = build_embedding_client(config)
        try:
            vectors = embedding_client.embeddings(model=embedding_model, inputs=[question])
        except OpenAIBackendError as exc:
            raise RuntimeError(f"Échec du calcul d'embedding pour la question: {exc}") from exc
        finally:
            embedding_client.close()

        if not vectors:
            raise RuntimeError("Embedding backend a renvoyé une réponse vide.")
        query_vec = _to_tuple(vectors[0])

        client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)
        results: List[SimilarRow] = []
        try:
            for table_name, table_cfg in config.tables.items():
                rows_payload = self._fetch_table_rows(client, table_name, table_cfg)
                columns, row_dicts = rows_payload
                if not row_dicts:
                    log.debug("Retrieval: table %s sans lignes exploitables.", table_name)
                    continue
                scored = self._score_table(
                    table=table_name,
                    table_cfg=table_cfg,
                    rows_payload=rows_payload,
                    query_vec=query_vec,
                    keep=max(top, 3),
                )
                results.extend(scored)
        finally:
            client.close()

        if not results:
            log.warning("Retrieval: aucune ligne similaire trouvée pour la question.")
            return []
        results.sort(key=lambda row: row.score, reverse=True)
        final = results[:top]
        log.info("Retrieval: sélectionné %d ligne(s) pour la rédaction (top_n=%d).", len(final), top)
        return final

    def _ensure_config(self) -> EmbeddingConfig:
        if self._config is None:
            cfg = load_embedding_config(self._config_path)
            if cfg is None or not cfg.tables:
                raise RuntimeError("Aucune configuration d'embeddings MindsDB disponible pour la récupération.")
            self._config = cfg
        return self._config

    def _fetch_table_rows(
        self,
        client: MindsDBClient,
        table_name: str,
        table_cfg: EmbeddingTableConfig,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        db_prefix = settings.nl2sql_db_prefix or "files"
        limit = settings.rag_table_row_cap
        sql = (
            f"SELECT * FROM {db_prefix}.{table_name} "
            f"WHERE {table_cfg.embedding_column} IS NOT NULL"
        )
        if limit:
            sql = f"{sql} LIMIT {limit}"
        log.debug("Retrieval: requête %s", sql)
        try:
            data = client.sql(sql)
        except Exception as exc:  # pragma: no cover - depends on backend
            raise RuntimeError(f"Échec de la requête MindsDB pour {table_name}: {exc}") from exc
        columns, rows = _normalize_result(data)
        return columns, _rows_as_dicts(columns, rows)

    def _score_table(
        self,
        *,
        table: str,
        table_cfg: EmbeddingTableConfig,
        rows_payload: tuple[list[str], list[dict[str, Any]]] | None,
        query_vec: Sequence[float],
        keep: int,
    ) -> List[SimilarRow]:
        if rows_payload is None:
            return []
        columns, rows = rows_payload
        scored: List[SimilarRow] = []
        for row in rows:
            raw_embedding = row.get(table_cfg.embedding_column)
            if raw_embedding is None:
                continue
            try:
                embedding_vec = _to_tuple(normalise_embedding(raw_embedding))
            except (ValueError, TypeError) as exc:
                log.warning("Retrieval: embedding invalide pour %s: %s", table, exc)
                continue
            if len(embedding_vec) != len(query_vec):
                log.warning(
                    "Retrieval: taille d'embedding incohérente (table=%s, attendu=%d, reçu=%d)",
                    table,
                    len(query_vec),
                    len(embedding_vec),
                )
                continue
            score = _cosine_similarity(query_vec, embedding_vec)
            if math.isinf(score) or math.isnan(score):
                continue
            sanitized = self._sanitize_row(row=row, columns=columns, table_cfg=table_cfg)
            focus = sanitized.get(table_cfg.source_column, "")
            scored.append(
                SimilarRow(
                    table=table,
                    score=score,
                    values=sanitized,
                    focus=_truncate(focus, limit=_SNIPPET_LIMIT),
                    source_column=table_cfg.source_column,
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:keep]

    def _sanitize_row(
        self,
        *,
        row: dict[str, Any],
        columns: list[str],
        table_cfg: EmbeddingTableConfig,
    ) -> dict[str, str]:
        sanitized: dict[str, str] = {}
        max_cols = settings.rag_max_columns

        def _maybe_add(column: str) -> None:
            if column == table_cfg.embedding_column:
                return
            if column in sanitized:
                return
            value = row.get(column)
            sanitized[column] = _stringify(value)

        # Prioritise the source column, then preserve CSV order.
        if table_cfg.source_column in row:
            _maybe_add(table_cfg.source_column)

        iterator = columns if columns else list(row.keys())
        for column in iterator:
            if len(sanitized) >= max_cols:
                break
            if column in sanitized or column == table_cfg.embedding_column:
                continue
            _maybe_add(column)

        # Enforce cap
        capped: dict[str, str] = {}
        for column, value in sanitized.items():
            capped[column] = value
            if len(capped) >= max_cols:
                break
        return capped


def _normalize_result(data: Any) -> tuple[list[str], list[Any]]:
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
    return [str(col) for col in columns or []], rows or []


def _rows_as_dicts(columns: list[str], rows: list[Any]) -> list[dict[str, Any]]:
    if not rows:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            mapping: dict[str, Any] = {}
            if columns:
                for col in columns:
                    key = str(col)
                    if key in row:
                        mapping[key] = row[key]
            else:
                for key, value in row.items():
                    mapping[str(key)] = value
            out.append(mapping)
            continue
        mapping: dict[str, Any] = {}
        for idx, col in enumerate(columns):
            if idx < len(row):
                mapping[str(col)] = row[idx]
        out.append(mapping)
    return out


def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return float("-inf")
    return dot / (norm_a * norm_b)


def _truncate(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + "…"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _to_tuple(vec: Iterable[float] | Sequence[float]) -> tuple[float, ...]:
    if isinstance(vec, tuple):
        return vec
    if isinstance(vec, list):
        return tuple(float(x) for x in vec)
    return tuple(float(x) for x in vec)
