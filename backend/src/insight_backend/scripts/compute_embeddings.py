from __future__ import annotations

import argparse
import logging
from typing import Iterable

from ..core.config import settings
from ..core.logging import configure_logging
from ..core.database import engine
from ..services.rag import EmbeddingPipeline


def _parse_tables(value: str | None) -> list[str]:
    if not value:
        return []
    items = [part.strip() for part in value.split(",")]
    return [item for item in items if item]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute embeddings for configured tables using SentenceTransformers."
    )
    parser.add_argument(
        "--tables",
        help="Optional comma-separated list of tables to process (overrides EMBEDDING_TABLES).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Override batch size used for embedding updates.",
    )
    parser.add_argument(
        "--model",
        help="Override embedding model name (defaults to EMBEDDING_MODEL).",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    configure_logging(settings.log_level)
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    tables = _parse_tables(args.tables)
    batch_size = args.batch_size or None
    model_name = args.model or None

    logging.getLogger("insight.services.rag.embedding").info(
        "Starting embedding computation (tables=%s, model=%s, batch=%s)",
        tables or settings.embedding_tables,
        model_name or settings.embedding_model,
        batch_size or settings.embedding_batch_size,
    )

    pipeline = EmbeddingPipeline(
        engine,
        settings,
        model_name=model_name,
        batch_size=batch_size,
    )
    pipeline.run(tables if tables else None)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
