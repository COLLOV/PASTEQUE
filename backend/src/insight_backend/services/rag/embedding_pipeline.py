from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer
from sqlalchemy import MetaData, Table, and_, bindparam, func, literal_column, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from tqdm.auto import tqdm

from ...core.config import Settings
from ...core.database import SessionLocal


log = logging.getLogger("insight.services.rag.embedding")


@dataclass
class TableContext:
    table: Table
    text_column: str
    vector_column: str


class EmbeddingPipeline:
    """Compute and persist embeddings for configured tables."""

    def __init__(
        self,
        engine: Engine,
        settings: Settings,
        *,
        model_name: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._model_name = model_name or settings.embedding_model
        self._batch_size = batch_size or settings.embedding_batch_size
        self._vector_column = settings.embedding_vector_column
        self._model: SentenceTransformer | None = None
        if not self._model_name:
            raise ValueError("Embedding model name cannot be empty")
        if self._batch_size <= 0:
            raise ValueError("Embedding batch size must be strictly positive")

    # Public API ---------------------------------------------------------

    def run(self, tables: Iterable[str] | None = None) -> None:
        targets = list(tables or self._settings.embedding_tables)
        if not targets:
            log.warning("No tables configured for embedding generation; nothing to do.")
            return

        self._ensure_vector_extension()
        for table_name in targets:
            try:
                self._process_table(table_name)
            except Exception:  # pragma: no cover - defensive logging for ops
                log.exception("Embedding generation failed for table '%s'", table_name)

    # Internal helpers ---------------------------------------------------

    def _ensure_vector_extension(self) -> None:
        with self._engine.begin() as connection:
            connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")

    def _process_table(self, table_name: str) -> None:
        ctx = self._prepare_table(table_name)
        if ctx is None:
            return

        pending = self._count_pending_rows(ctx.table, ctx.text_column, ctx.vector_column)
        if pending == 0:
            log.info("Table '%s': no rows pending embedding.", table_name)
            return

        progress = tqdm(total=pending, desc=f"{table_name}", unit="row")
        try:
            while True:
                batch = self._fetch_batch(ctx.table, ctx.text_column, ctx.vector_column)
                if not batch:
                    break
                payloads = self._build_updates(batch)
                if payloads:
                    self._apply_updates(ctx.table, payloads)
                progress.update(len(batch))
        finally:
            progress.close()

        log.info("Table '%s': embeddings generated for %d rows.", table_name, pending)

    def _prepare_table(self, table_name: str) -> TableContext | None:
        metadata = MetaData()
        try:
            table = Table(table_name, metadata, autoload_with=self._engine)
        except SQLAlchemyError:
            log.warning("Table '%s' not found in database; skipping.", table_name)
            return None

        text_column = self._settings.embedding_column_for(table_name)
        if text_column not in table.c:
            log.warning(
                "Table '%s': text column '%s' missing; skipping embedding.",
                table_name,
                text_column,
            )
            return None

        if self._vector_column not in table.c:
            self._ensure_vector_column(table_name)
            metadata = MetaData()
            table = Table(table_name, metadata, autoload_with=self._engine)

        self._verify_vector_column(table_name)
        return TableContext(table=table, text_column=text_column, vector_column=self._vector_column)

    def _ensure_vector_column(self, table_name: str) -> None:
        dim = self._settings.embedding_dim
        qualified = self._quote_identifier(table_name)
        column = self._quote_identifier(self._vector_column)
        statement = f"ALTER TABLE {qualified} ADD COLUMN IF NOT EXISTS {column} vector({dim})"
        with self._engine.begin() as connection:
            connection.exec_driver_sql(statement)
        log.info(
            "Table '%s': ensured vector column '%s' with dimension %d.",
            table_name,
            self._vector_column,
            dim,
        )

    def _verify_vector_column(self, table_name: str) -> None:
        sql = (
            "SELECT t.typname, a.atttypmod "
            "FROM pg_attribute a "
            "JOIN pg_class c ON a.attrelid = c.oid "
            "JOIN pg_type t ON a.atttypid = t.oid "
            "WHERE c.oid = to_regclass(:table_name) "
            "AND a.attname = :column_name "
            "AND a.attisdropped = FALSE"
        )
        with self._engine.connect() as connection:
            row = connection.execute(
                text(sql),
                {"table_name": table_name, "column_name": self._vector_column},
            ).first()
        if row is None:
            raise RuntimeError(
                f"Vector column '{self._vector_column}' not found after creation on table '{table_name}'."
            )
        typname, atttypmod = row
        if typname != "vector":
            raise RuntimeError(
                f"Column '{self._vector_column}' on table '{table_name}' is of type '{typname}', expected 'vector'."
            )
        dim = int(atttypmod) - 4 if atttypmod else None
        if dim is not None and dim != self._settings.embedding_dim:
            raise RuntimeError(
                "Table '%s': vector column '%s' dimension %s does not match configured %s."
                % (table_name, self._vector_column, dim, self._settings.embedding_dim)
            )

    def _count_pending_rows(self, table: Table, text_column: str, vector_column: str) -> int:
        condition = and_(
            table.c[vector_column].is_(None),
            table.c[text_column].is_not(None),
            func.btrim(table.c[text_column]) != "",
        )
        with SessionLocal() as session:
            stmt = select(func.count()).select_from(table).where(condition)
            return int(session.execute(stmt).scalar_one())

    def _fetch_batch(self, table: Table, text_column: str, vector_column: str) -> list[tuple[object, str]]:
        condition = and_(
            table.c[vector_column].is_(None),
            table.c[text_column].is_not(None),
            func.btrim(table.c[text_column]) != "",
        )
        stmt = (
            select(literal_column("ctid"), table.c[text_column])
            .where(condition)
            .limit(self._batch_size)
        )
        with SessionLocal() as session:
            rows = session.execute(stmt).all()
            return [(row[0], str(row[1])) for row in rows]

    def _build_updates(self, rows: Sequence[tuple[object, str]]) -> list[dict[str, object]]:
        if not rows:
            return []
        model = self._load_model()
        texts = [text for _, text in rows]
        vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        if not isinstance(vectors, np.ndarray):
            vectors = np.array(vectors)
        vectors = vectors.astype("float32", copy=False)
        payloads: list[dict[str, object]] = []
        for (ctid, _), vector in zip(rows, vectors):
            payloads.append({"ctid": ctid, "embedding": vector.tolist()})
        return payloads

    def _apply_updates(self, table: Table, payloads: list[dict[str, object]]) -> None:
        update_stmt = (
            table.update()
            .where(literal_column("ctid") == bindparam("ctid"))
            .values({self._vector_column: bindparam("embedding")})
        )
        with SessionLocal() as session:
            session.execute(update_stmt, payloads)
            session.commit()

    def _load_model(self) -> SentenceTransformer:
        if self._model is None:
            log.info("Loading embedding model '%s'", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @staticmethod
    def _quote_identifier(name: str) -> str:
        if not name or any(ch in '"' for ch in name):
            raise ValueError(f"Unsafe identifier: {name!r}")
        if not all(ch.isalnum() or ch == "_" for ch in name):
            raise ValueError(f"Identifier contains unsupported characters: {name!r}")
        return f'"{name}"'
