from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import yaml

from ..core.config import resolve_project_path, settings
from ..integrations.openai_client import OpenAICompatibleClient


log = logging.getLogger("insight.services.mindsdb_embeddings")


def resolve_embedding_mode() -> str:
    """Return the configured embedding mode, falling back to LLM mode."""
    raw = settings.embedding_mode or settings.llm_mode
    mode = (raw or "").strip().lower()
    if mode not in {"local", "api"}:
        raise RuntimeError("EMBEDDING_MODE/LLM_MODE must be 'local' or 'api' to compute embeddings.")
    return mode


@dataclass(frozen=True)
class EmbeddingTableConfig:
    source_column: str
    embedding_column: str
    model: str | None = None


@dataclass(frozen=True)
class EmbeddingConfig:
    tables: dict[str, EmbeddingTableConfig]
    default_model: str
    batch_size: int


def load_embedding_config(raw_path: str | None) -> EmbeddingConfig | None:
    """Parse the YAML configuration describing MindsDB embedding columns."""
    if not raw_path:
        log.info("MINDSDB_EMBEDDINGS_CONFIG_PATH not set; embeddings will be unavailable.")
        return None

    resolved = Path(resolve_project_path(raw_path))
    if not resolved.exists():
        raise FileNotFoundError(f"MindsDB embedding config not found: {resolved}")

    with resolved.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ValueError("MindsDB embedding config must be a mapping at the top level.")

    default_model = data.get("default_model")
    if default_model is not None and not isinstance(default_model, str):
        raise ValueError("default_model must be a string when provided.")

    batch_size = data.get("batch_size", settings.mindsdb_embedding_batch_size)
    if not isinstance(batch_size, int) or batch_size <= 0:
        raise ValueError("batch_size must be a positive integer.")

    tables_section = data.get("tables") or {}
    if not isinstance(tables_section, dict):
        raise ValueError("tables must be a mapping of table names.")

    tables: dict[str, EmbeddingTableConfig] = {}
    for table_name, table_config in tables_section.items():
        if not isinstance(table_name, str):
            raise ValueError("Table names in the embedding config must be strings.")
        if not isinstance(table_config, dict):
            raise ValueError(f"Configuration for table {table_name!r} must be a mapping.")
        source_column = table_config.get("source_column")
        embedding_column = table_config.get("embedding_column")
        model = table_config.get("model")
        if not source_column or not isinstance(source_column, str):
            raise ValueError(f"Table {table_name!r} requires a string 'source_column'.")
        if not embedding_column or not isinstance(embedding_column, str):
            raise ValueError(f"Table {table_name!r} requires a string 'embedding_column'.")
        if model is not None and not isinstance(model, str):
            raise ValueError(f"Table {table_name!r} has an invalid 'model' value (must be string).")
        tables[table_name] = EmbeddingTableConfig(
            source_column=source_column,
            embedding_column=embedding_column,
            model=model,
        )

    if not tables:
        log.warning("Embedding config %s defines no tables. Embeddings will be ignored.", resolved)
        return None

    resolved_default = default_embedding_model(default_model)
    log.info(
        "Loaded embedding config from %s (%d table(s), batch_size=%d, default_model=%s)",
        resolved,
        len(tables),
        batch_size,
        resolved_default,
    )
    return EmbeddingConfig(tables=tables, default_model=resolved_default, batch_size=batch_size)


def default_embedding_model(configured: str | None) -> str:
    """Return the embedding model that should be used given current settings."""
    mode = resolve_embedding_mode()
    if mode == "local":
        candidate = configured or settings.embedding_model or settings.z_local_model
    elif mode == "api":
        candidate = configured or settings.embedding_model or settings.llm_model
    if not candidate:
        raise RuntimeError("No embedding model configured (check EMBEDDING_MODEL or default model).")
    return candidate


def build_embedding_client(config: EmbeddingConfig) -> tuple[OpenAICompatibleClient, str]:
    """Instantiate the OpenAI-compatible client used for embeddings."""
    mode = resolve_embedding_mode()
    if mode == "local":
        base_url = settings.vllm_base_url
        api_key = None
    elif mode == "api":
        base_url = settings.openai_base_url
        api_key = settings.openai_api_key
    if not base_url:
        raise RuntimeError("Embedding backend base URL is missing.")
    timeout = settings.openai_timeout_s
    client = OpenAICompatibleClient(base_url=base_url, api_key=api_key, timeout_s=timeout)
    model = config.default_model
    log.info("Initialised embedding backend (mode=%s, base_url=%s, model=%s)", mode, base_url, model)
    return client, model


def normalise_embedding(value: object) -> Iterable[float]:
    """Convert embedding payloads (list or JSON string) into a float iterator."""
    if isinstance(value, str):
        raw = json.loads(value)
    else:
        raw = value
    if not isinstance(raw, (list, tuple)):
        raise ValueError(f"Unexpected embedding payload: {type(raw)!r}")
    for item in raw:
        yield float(item)
