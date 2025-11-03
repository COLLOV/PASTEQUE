from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm

from ...core.config import settings
from ...integrations.mindsdb_client import MindsDBClient

log = logging.getLogger("insight.services.rag.embedding")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DEFAULT_DATABASE = "files"


def _quote_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f"`{name}`"


def _escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


@dataclass
class EmbeddingTableConfig:
    table: str
    text_column: str
    id_column: str = "id"
    embedding_column: str = "embedding_vector"
    database: str | None = None

    def __post_init__(self) -> None:
        if "." in self.table:
            if self.database:
                raise ValueError("Provide either `table` with database prefix or `database`, not both.")
            database, table_name = self.table.split(".", 1)
            self.database = database
            self.table = table_name


class EmbeddingManager:
    def __init__(self, *, client: MindsDBClient | None = None):
        self.client = client or MindsDBClient(
            base_url=settings.mindsdb_base_url,
            token=settings.mindsdb_token,
        )
        self._owns_client = client is None
        self._model: SentenceTransformer | None = None
        self._batch_size = max(1, settings.embedding_batch_size)
        self._dimension = settings.embedding_dimension

    def __enter__(self) -> EmbeddingManager:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            log.info(
                "Loading embedding model %s on device %s",
                settings.embedding_model,
                settings.embedding_device,
            )
            self._model = SentenceTransformer(
                settings.embedding_model,
                device=settings.embedding_device,
            )
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
        if cfg.database and not _IDENTIFIER_RE.match(cfg.database):
            raise ValueError(f"Invalid database identifier: {cfg.database!r}")

    def _prepare(self, cfg: EmbeddingTableConfig) -> None:
        database = self._resolve_database(cfg)
        cfg.database = database
        self._ensure_embedding_column(cfg)

    def _process(self, cfg: EmbeddingTableConfig) -> None:
        total = self._count_pending(cfg)
        qualified = self._qualified_table(cfg)
        if total == 0:
            log.info("No embeddings to compute for %s (already up to date).", qualified)
            return

        progress = tqdm(total=total, desc=f"{qualified}", unit="row")
        while True:
            rows = self._fetch_pending_batch(cfg)
            if not rows:
                break
            texts = [str(row["text_value"]) for row in rows]
            vectors = self._encode(texts)
            for idx, row in enumerate(rows):
                embedding_sql = self._vector_literal(vectors[idx])
                identifier = self._literal(row["id"])
                update_sql = (
                    f"UPDATE {qualified} "
                    f"SET {_quote_identifier(cfg.embedding_column)} = {embedding_sql} "
                    f"WHERE {_quote_identifier(cfg.id_column)} = {identifier}"
                )
                self._execute(update_sql)
            progress.update(len(rows))

        progress.close()
        log.info("Computed embeddings for %s (rows=%d).", qualified, total)

    def _fetch_pending_batch(self, cfg: EmbeddingTableConfig) -> list[dict[str, Any]]:
        qualified = self._qualified_table(cfg)
        select_sql = (
            f"SELECT "
            f"{_quote_identifier(cfg.id_column)} AS id, "
            f"{_quote_identifier(cfg.text_column)} AS text_value "
            f"FROM {qualified} "
            f"WHERE {_quote_identifier(cfg.text_column)} IS NOT NULL "
            f"AND {_quote_identifier(cfg.embedding_column)} IS NULL "
            f"ORDER BY {_quote_identifier(cfg.id_column)} "
            f"LIMIT {self._batch_size}"
        )
        columns, rows = self._execute(select_sql)
        if not rows:
            return []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                normalized.append(row)
            else:
                normalized.append({columns[idx]: row[idx] for idx in range(len(columns))})
        return normalized

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
        count_sql = (
            f"SELECT COUNT(*) AS pending_count FROM {qualified} "
            f"WHERE {_quote_identifier(cfg.text_column)} IS NOT NULL "
            f"AND {_quote_identifier(cfg.embedding_column)} IS NULL"
        )
        columns, rows = self._execute(count_sql)
        if not rows:
            return 0
        row = rows[0]
        if isinstance(row, dict):
            value = next(iter(row.values()))
        else:
            idx = columns.index("pending_count") if "pending_count" in columns else 0
            value = row[idx]
        return int(value or 0)

    def _resolve_database(self, cfg: EmbeddingTableConfig) -> str:
        if cfg.database:
            return cfg.database
        lookup_sql = (
            "SELECT table_schema "
            "FROM information_schema.tables "
            f"WHERE table_name = '{_escape_literal(cfg.table)}' "
            "ORDER BY CASE WHEN table_schema = 'files' THEN 0 ELSE 1 END "
            "LIMIT 1"
        )
        _, rows = self._execute(lookup_sql)
        if not rows:
            raise ValueError(f"Table {cfg.table!r} not found in MindsDB catalogs.")
        row = rows[0]
        schema = row["table_schema"] if isinstance(row, dict) else row[0]
        return str(schema or _DEFAULT_DATABASE)

    def _ensure_embedding_column(self, cfg: EmbeddingTableConfig) -> None:
        qualified = self._qualified_table(cfg)
        column_sql = (
            "SELECT column_type "
            "FROM information_schema.columns "
            f"WHERE table_schema = '{_escape_literal(cfg.database or _DEFAULT_DATABASE)}' "
            f"AND table_name = '{_escape_literal(cfg.table)}' "
            f"AND column_name = '{_escape_literal(cfg.embedding_column)}' "
            "LIMIT 1"
        )
        _, rows = self._execute(column_sql)
        expected = f"vector({self._dimension})"
        if not rows:
            alter_sql = (
                f"ALTER TABLE {qualified} "
                f"ADD COLUMN {_quote_identifier(cfg.embedding_column)} VECTOR({self._dimension})"
            )
            self._execute(alter_sql)
            log.info("Added column %s.%s.", qualified, cfg.embedding_column)
            return
        row = rows[0]
        column_type = row["column_type"] if isinstance(row, dict) else row[0]
        if str(column_type).lower() != expected:
            raise RuntimeError(
                f"Column {qualified}.{cfg.embedding_column} has type {column_type}, expected {expected}."
            )

    def _qualified_table(self, cfg: EmbeddingTableConfig) -> str:
        database = cfg.database or _DEFAULT_DATABASE
        return f"{_quote_identifier(database)}.{_quote_identifier(cfg.table)}"

    def _execute(self, sql: str) -> tuple[list[str], list[Any]]:
        data = self.client.sql(sql)
        columns: list[Any] = []
        rows: list[Any] = []
        if isinstance(data, dict):
            if data.get("type") == "table":
                columns = data.get("column_names") or []
                rows = data.get("data") or []
            if not rows:
                rows = data.get("result", {}).get("rows") or data.get("rows") or rows
            if not columns:
                columns = data.get("result", {}).get("columns") or data.get("columns") or columns
        return list(columns or []), list(rows or [])

    def _literal(self, value: Any) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, np.generic):
            return self._literal(value.item())
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        return f"'{_escape_literal(str(value))}'"

    @staticmethod
    def _vector_literal(values: Sequence[float]) -> str:
        payload = json.dumps([float(v) for v in values], separators=(",", ":"))
        return f"TO_VECTOR('{payload}')"
