from __future__ import annotations

from typing import Sequence

from ...core.config import settings
from ...core.database import engine


def quote_identifier(name: str) -> str:
    """Quote a potentially qualified identifier."""
    preparer = engine.dialect.identifier_preparer
    parts = [p for p in name.split(".") if p]
    return ".".join(preparer.quote_identifier(part) for part in parts)


def vector_literal(values: Sequence[float]) -> str:
    """Serialize a vector into pgvector textual representation."""
    comps: list[str] = []
    for v in values:
        text_val = f"{float(v):.12f}"
        if "." in text_val:
            text_val = text_val.rstrip("0").rstrip(".")
        comps.append(text_val or "0")
    return f"[{','.join(comps)}]"


def parse_schema_table(qualified: str) -> tuple[str | None, str]:
    """Split `schema.table` into components."""
    if "." in qualified:
        schema, table = qualified.split(".", 1)
        return schema, table
    return None, qualified


def resolve_text_column(table: str, stem: str) -> str:
    """Resolve the text column to embed for a table."""
    overrides = settings.rag_text_column_overrides
    candidates = [table, table.split(".")[-1], stem]
    for key in candidates:
        if key in overrides:
            return overrides[key]
    return settings.rag_text_column_default
