from __future__ import annotations

import argparse
import logging
from typing import List

from ..core.config import settings
from ..core.logging import configure_logging
from ..services.rag.embedding_service import EmbeddingManager, EmbeddingTableConfig

log = logging.getLogger("insight.scripts.compute_embeddings")


def _parse_table(arg: str) -> EmbeddingTableConfig:
    parts = [segment.strip() for segment in arg.split(":")]
    if len(parts) < 2:
        raise argparse.ArgumentTypeError(
            "Expected format '[schema.]table:text_column[:id_column][:embedding_column]'."
        )
    table = parts[0]
    text_column = parts[1]
    id_column = parts[2] if len(parts) >= 3 and parts[2] else "id"
    embedding_column = parts[3] if len(parts) >= 4 and parts[3] else "embedding_vector"
    return EmbeddingTableConfig(
        table=table,
        text_column=text_column,
        id_column=id_column,
        embedding_column=embedding_column,
    )


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compute sentence-transformer embeddings for configured tables. "
            "Use multiple --table flags to cover all sources. Example:\n"
            "  uv run python -m insight_backend.scripts.compute_embeddings "
            "--table public.tickets:description:ticket_id:description_embedding"
        )
    )
    parser.add_argument(
        "--table",
        dest="tables",
        action="append",
        required=True,
        help="[schema.]table:text_column[:id_column][:embedding_column] mapping (repeatable).",
    )
    args = parser.parse_args(argv)

    configure_logging(settings.log_level)
    configs = [_parse_table(raw) for raw in args.tables]
    log.info("Starting embedding computation for %d table(s).", len(configs))
    for cfg in configs:
        schema_label = cfg.schema or "<auto>"
        log.info(
            "Table config schema=%s table=%s text_column=%s id_column=%s embedding_column=%s",
            schema_label,
            cfg.table,
            cfg.text_column,
            cfg.id_column,
            cfg.embedding_column,
        )

    manager = EmbeddingManager()
    manager.compute_embeddings(configs)


if __name__ == "__main__":
    main()
