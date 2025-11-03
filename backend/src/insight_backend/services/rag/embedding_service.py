from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql.elements import TextClause
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm

from ...core.config import settings
from ...core.database import engine as default_engine

log = logging.getLogger("insight.services.rag.embedding")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f'"{name}"'


@dataclass
class EmbeddingTableConfig:
    table: str
    text_column: str
    id_column: str = "id"
    embedding_column: str = "embedding_vector"
    schema: str | None = None

    def __post_init__(self) -> None:
        if "." in self.table:
            if self.schema:
                raise ValueError("Provide either `table` with schema prefix or `schema`, not both.")
            schema, table_name = self.table.split(".", 1)
            self.schema = schema
            self.table = table_name


class EmbeddingManager:
    def __init__(self, *, engine: Engine | None = None):
        self.engine = engine or default_engine
        self._model: SentenceTransformer | None = None
        self._batch_size = max(1, settings.embedding_batch_size)
        self._dimension = settings.embedding_dimension

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            log.info("Loading embedding model %s on device %s", settings.embedding_model, settings.embedding_device)
            self._model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
        return self._model

    def compute_embeddings(self, configs: Iterable[EmbeddingTableConfig]) -> None:
        for cfg in configs:
            self._validate_config(cfg)
            self._prepare(cfg)
            self._process(cfg)

    def _validate_config(self, cfg: EmbeddingTableConfig) -> None:
        for name in (cfg.table, cfg.text_column, cfg.id_column, cfg.embedding_column):
            if not _IDENTIFIER_RE.match(name):
                raise ValueError(f"Invalid identifier: {name!r}")
        if cfg.schema and not _IDENTIFIER_RE.match(cfg.schema):
            raise ValueError(f"Invalid schema identifier: {cfg.schema!r}")

    def _prepare(self, cfg: EmbeddingTableConfig) -> None:
        with self.engine.begin() as conn:
            self._ensure_vector_extension(conn)
            schema = self._ensure_schema(conn, cfg)
            cfg.schema = schema
            self._ensure_embedding_column(conn, cfg)

    def _process(self, cfg: EmbeddingTableConfig) -> None:
        total = self._count_pending(cfg)
        qualified = self._qualified_table(cfg)
        if total == 0:
            log.info("No embeddings to compute for %s (already up to date).", qualified)
            return

        progress = tqdm(total=total, desc=f"{qualified}", unit="row")
        select_sql = text(
            f"""
            SELECT {_quote_identifier(cfg.id_column)} AS id, {_quote_identifier(cfg.text_column)} AS text_value
            FROM {qualified}
            WHERE {_quote_identifier(cfg.text_column)} IS NOT NULL
              AND {_quote_identifier(cfg.embedding_column)} IS NULL
            ORDER BY {_quote_identifier(cfg.id_column)}
            LIMIT :limit
            """
        )
        update_sql = text(
            f"""
            UPDATE {qualified}
            SET {_quote_identifier(cfg.embedding_column)} = :embedding::vector
            WHERE {_quote_identifier(cfg.id_column)} = :id
            """
        )

        while True:
            rows = self._fetch_pending_batch(select_sql)
            if not rows:
                break
            vectors = self._encode([row["text_value"] for row in rows])
            payload = [
                {"id": rows[idx]["id"], "embedding": self._vector_literal(vectors[idx])}
                for idx in range(len(rows))
            ]
            with self.engine.begin() as conn:
                conn.execute(update_sql, payload)
            progress.update(len(rows))

        progress.close()
        log.info("Computed embeddings for %s (rows=%d).", qualified, total)

    def _fetch_pending_batch(self, stmt: TextClause) -> list[dict[str, object]]:
        with self.engine.connect() as conn:
            result = conn.execute(stmt, {"limit": self._batch_size})
            rows = result.mappings().all()
        return rows

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(
            list(texts),
            batch_size=min(self._batch_size, len(texts)),
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=False,
        )
        array = np.asarray(embeddings, dtype=float)
        if array.ndim != 2 or array.shape[1] != self._dimension:
            raise RuntimeError(
                f"Model returned embeddings with shape {array.shape}, expected (*, {self._dimension})."
            )
        if not np.all(np.isfinite(array)):
            raise ValueError("Non-finite values detected in embeddings.")
        return array.tolist()

    def _count_pending(self, cfg: EmbeddingTableConfig) -> int:
        qualified = self._qualified_table(cfg)
        count_sql = text(
            f"""
            SELECT COUNT(*) FROM {qualified}
            WHERE {_quote_identifier(cfg.text_column)} IS NOT NULL
              AND {_quote_identifier(cfg.embedding_column)} IS NULL
            """
        )
        with self.engine.connect() as conn:
            total = conn.execute(count_sql).scalar_one()
        return int(total)

    def _ensure_vector_extension(self, conn: Connection) -> None:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    def _ensure_schema(self, conn: Connection, cfg: EmbeddingTableConfig) -> str:
        if cfg.schema:
            return cfg.schema
        schema = conn.execute(
            text(
                """
                SELECT table_schema
                FROM information_schema.tables
                WHERE table_name = :table
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY CASE WHEN table_schema = 'public' THEN 0 ELSE 1 END
                LIMIT 1
                """
            ),
            {"table": cfg.table},
        ).scalar_one_or_none()
        if not schema:
            raise ValueError(f"Table {cfg.table!r} not found in any user schema.")
        return str(schema)

    def _ensure_embedding_column(self, conn: Connection, cfg: EmbeddingTableConfig) -> None:
        qualified = self._qualified_table(cfg)
        existing = conn.execute(
            text(
                """
                SELECT pg_catalog.format_type(a.atttypid, a.atttypmod) AS formatted_type
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = :schema
                  AND c.relname = :table
                  AND a.attname = :column
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                """
            ),
            {"schema": cfg.schema, "table": cfg.table, "column": cfg.embedding_column},
        ).scalar_one_or_none()

        expected = f"vector({self._dimension})"
        if existing is None:
            conn.execute(
                text(
                    f"ALTER TABLE {qualified} "
                    f"ADD COLUMN {_quote_identifier(cfg.embedding_column)} vector({self._dimension})"
                )
            )
            log.info("Added column %s.%s.", qualified, cfg.embedding_column)
            return
        if existing != expected:
            raise RuntimeError(
                f"Column {qualified}.{cfg.embedding_column} has type {existing}, expected {expected}."
            )

    def _qualified_table(self, cfg: EmbeddingTableConfig) -> str:
        if cfg.schema:
            return f"{_quote_identifier(cfg.schema)}.{_quote_identifier(cfg.table)}"
        return _quote_identifier(cfg.table)

    @staticmethod
    def _vector_literal(values: Sequence[float]) -> str:
        return "[" + ",".join(f"{v:.8f}" for v in values) + "]"
