from __future__ import annotations

import argparse
import logging
from typing import Dict, Iterable

from sqlalchemy import text
from tqdm import tqdm

from ..core.config import settings
from ..core.database import engine, discover_rag_tables, ensure_vector_schema
from ..services.rag.common import (
    parse_schema_table,
    quote_identifier,
    resolve_text_column,
    vector_literal,
)
from ..services.rag.encoder import EmbeddingBackend

log = logging.getLogger("insight.scripts.embed")


def _column_exists(conn, schema: str | None, table: str, column: str) -> bool:
    if schema:
        sql = text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table AND column_name = :column
            LIMIT 1
            """
        )
        row = conn.execute(sql, {"schema": schema, "table": table, "column": column}).first()
    else:
        sql = text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = :table AND column_name = :column
            LIMIT 1
            """
        )
        row = conn.execute(sql, {"table": table, "column": column}).first()
    return bool(row)


class EmbeddingJob:
    def __init__(self, *, tables_filter: Iterable[str] | None, limit: int | None):
        self.tables_filter = set(tables_filter or [])
        self.limit = limit if (limit and limit > 0) else None
        self.backend = EmbeddingBackend(
            model_name=settings.rag_embedding_model,
            normalize=settings.rag_distance == "cosine",
            batch_size=max(1, settings.rag_embedding_batch_size),
        )

    def run(self) -> None:
        ensure_vector_schema()
        mapping = discover_rag_tables()
        if not mapping:
            log.info("No tables available for embedding generation; nothing to do.")
            return
        selected = self._select_tables(mapping)
        if not selected:
            log.warning("No matching tables after applying filters: %s", sorted(self.tables_filter))
            return
        log.info(
            "Embedding job start: tables=%s model=%s batch=%d limit=%s",
            ", ".join(selected.keys()),
            self.backend.model_name,
            self.backend.batch_size,
            self.limit or "-",
        )
        remaining_global = self.limit
        with engine.connect() as conn:
            for table_name, stem in selected.items():
                if remaining_global is not None and remaining_global <= 0:
                    break
                processed, remaining_global = self._process_table(conn, table_name, stem, remaining_global)
                log.info("Table %s: embedded %d rows", table_name, processed)
        log.info("Embedding job completed.")

    def _select_tables(self, mapping: Dict[str, str]) -> Dict[str, str]:
        if not self.tables_filter:
            return mapping
        resolved: dict[str, str] = {}
        for item in self.tables_filter:
            if item in mapping:
                resolved[item] = mapping[item]
                continue
            matches = [table for table, stem in mapping.items() if stem == item or table.endswith(f".{item}")]
            if matches:
                for table in matches:
                    resolved[table] = mapping[table]
            else:
                log.warning("Requested table '%s' not found; skipping.", item)
        return resolved

    def _process_table(self, conn, qualified: str, stem: str, remaining_global: int | None) -> tuple[int, int | None]:
        schema, table = parse_schema_table(qualified)
        text_column = resolve_text_column(qualified, stem)
        if not _column_exists(conn, schema, table, "id"):
            log.warning("Skipping %s: missing 'id' column.", qualified)
            return 0, remaining_global
        if not _column_exists(conn, schema, table, text_column):
            log.warning("Skipping %s: missing text column '%s'.", qualified, text_column)
            return 0, remaining_global

        table_sql = quote_identifier(qualified)
        column_sql = quote_identifier(text_column)
        count_sql = text(
            f"""
            SELECT COUNT(*) FROM {table_sql}
            WHERE embedding IS NULL
              AND {column_sql} IS NOT NULL
              AND btrim({column_sql}) <> ''
            """
        )
        total = conn.execute(count_sql).scalar_one()
        if not total:
            return 0, remaining_global
        if remaining_global is not None:
            total = min(total, remaining_global)
        progress = tqdm(total=total, desc=f"{qualified}", unit="row")
        processed = 0
        select_sql = text(
            f"""
            SELECT id, {column_sql} AS payload
            FROM {table_sql}
            WHERE embedding IS NULL
              AND {column_sql} IS NOT NULL
              AND btrim({column_sql}) <> ''
            ORDER BY id
            LIMIT :limit
            """
        )
        update_sql = text(
            f"UPDATE {table_sql} SET embedding = :embedding::vector WHERE id = :id"
        )
        chunk_limit = self.backend.batch_size
        commit_every = max(1, settings.rag_commit_every)
        try:
            while True:
                if remaining_global is not None and remaining_global <= 0:
                    break
                fetch_limit = min(chunk_limit, remaining_global) if remaining_global else chunk_limit
                rows = conn.execute(select_sql, {"limit": fetch_limit}).fetchall()
                if not rows:
                    break
                texts = [row.payload for row in rows if row.payload and row.payload.strip()]
                if not texts:
                    ids = [row.id for row in rows]
                    if ids:
                        conn.execute(
                            text(
                                f"UPDATE {table_sql} SET embedding = NULL WHERE id = ANY(:ids)"
                            ),
                            {"ids": ids},
                        )
                    break
                vectors = self.backend.embed(texts)
                # Align lengths (rows without text should be skipped)
                payloads = []
                idx = 0
                for row in rows:
                    content = row.payload
                    if not content or not content.strip():
                        continue
                    payloads.append({"id": row.id, "embedding": vector_literal(vectors[idx])})
                    idx += 1
                if not payloads:
                    break
                tx = conn.begin()
                try:
                    for chunk_start in range(0, len(payloads), commit_every):
                        chunk = payloads[chunk_start : chunk_start + commit_every]
                        conn.execute(update_sql, chunk)
                    tx.commit()
                except Exception:
                    tx.rollback()
                    raise
                processed += len(payloads)
                progress.update(len(payloads))
                if remaining_global is not None:
                    remaining_global -= len(payloads)
        finally:
            progress.close()
        return processed, remaining_global


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill pgvector embeddings for raw data tables.")
    parser.add_argument(
        "--table",
        action="append",
        help="Restrict to this table (stem or fully-qualified name). Can be passed multiple times.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Stop after embedding this many rows globally.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parse_args()
    job = EmbeddingJob(tables_filter=args.table, limit=args.limit)
    job.run()


if __name__ == "__main__":
    main()
