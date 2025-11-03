from __future__ import annotations

import csv
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
import yaml

from ..core.config import resolve_project_path, settings
from ..integrations.mindsdb_client import MindsDBClient
from ..integrations.openai_client import OpenAIBackendError, OpenAICompatibleClient
from ..repositories.data_repository import DataRepository


log = logging.getLogger("insight.services.mindsdb_sync")


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


def sync_all_tables() -> list[str]:
    repo = DataRepository(tables_dir=Path(settings.tables_dir))
    files = list(repo._iter_table_files())
    if not files:
        log.info("No tables found in %s", repo.tables_dir)
        return []

    config = _load_embedding_config(settings.mindsdb_embeddings_config_path)

    embedding_client: OpenAICompatibleClient | None = None
    embedding_default_model: str | None = None
    if config and config.tables:
        available = {p.stem for p in files}
        missing = sorted(set(config.tables.keys()) - available)
        if missing:
            raise FileNotFoundError(
                f"MindsDB embedding configuration references missing tables: {', '.join(missing)}"
            )
        embedding_client, embedding_default_model = _build_embedding_client(config)

    client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)
    uploaded: list[str] = []
    try:
        for path in files:
            table_name = path.stem
            table_cfg = config.tables.get(table_name) if config else None
            tmp_path: Path | None = None
            try:
                if table_cfg:
                    if embedding_client is None or embedding_default_model is None:
                        raise RuntimeError("Embedding client not initialised.")
                    tmp_path = _augment_with_embeddings(
                        source_path=path,
                        table_name=table_name,
                        table_cfg=table_cfg,
                        client=embedding_client,
                        default_model=embedding_default_model,
                        batch_size=config.batch_size,
                    )
                    upload_source = tmp_path
                    log.info(
                        "Uploading %s with embeddings (%s → %s, model=%s)",
                        table_name,
                        table_cfg.source_column,
                        table_cfg.embedding_column,
                        table_cfg.model or embedding_default_model,
                    )
                else:
                    upload_source = path
                    log.info("Uploading %s without embeddings", table_name)
                client.upload_file(upload_source)
                uploaded.append(path.name)
            finally:
                if tmp_path:
                    tmp_path.unlink(missing_ok=True)
    finally:
        client.close()
        if embedding_client:
            embedding_client.close()

    log.info("Uploaded %d tables to MindsDB", len(uploaded))
    return uploaded


def _load_embedding_config(raw_path: str | None) -> EmbeddingConfig | None:
    if not raw_path:
        log.info("MINDSDB_EMBEDDINGS_CONFIG_PATH not set; tables will be uploaded without embeddings.")
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
        log.warning("Embedding config %s defines no tables. Uploading without embeddings.", resolved)
        return None

    resolved_default = _default_embedding_model(default_model)
    log.info(
        "Loaded embedding config from %s (%d table(s), batch_size=%d, default_model=%s)",
        resolved,
        len(tables),
        batch_size,
        resolved_default,
    )
    return EmbeddingConfig(tables=tables, default_model=resolved_default, batch_size=batch_size)


def _default_embedding_model(configured: str | None) -> str:
    mode = (settings.llm_mode or "").strip().lower()
    if mode == "local":
        candidate = configured or settings.embedding_model or settings.z_local_model
    elif mode == "api":
        candidate = configured or settings.embedding_model or settings.llm_model
    else:
        raise RuntimeError("LLM_MODE must be 'local' or 'api' to compute embeddings.")
    if not candidate:
        raise RuntimeError("No embedding model configured (check EMBEDDING_MODEL or default model).")
    return candidate


def _build_embedding_client(config: EmbeddingConfig) -> tuple[OpenAICompatibleClient, str]:
    mode = (settings.llm_mode or "").strip().lower()
    if mode == "local":
        base_url = settings.vllm_base_url
        api_key = None
    elif mode == "api":
        base_url = settings.openai_base_url
        api_key = settings.openai_api_key
    else:
        raise RuntimeError("LLM_MODE must be 'local' or 'api' to compute embeddings.")

    if not base_url:
        raise RuntimeError(f"Embedding backend base URL missing for LLM_MODE={settings.llm_mode!r}.")

    client = OpenAICompatibleClient(
        base_url=base_url,
        api_key=api_key,
        timeout_s=settings.openai_timeout_s,
    )
    log.info("Initialised embedding backend (mode=%s, base_url=%s)", mode, base_url)
    return client, config.default_model


def _augment_with_embeddings(
    *,
    source_path: Path,
    table_name: str,
    table_cfg: EmbeddingTableConfig,
    client: OpenAICompatibleClient,
    default_model: str,
    batch_size: int,
) -> Path:
    delimiter = "," if source_path.suffix.lower() == ".csv" else "\t"
    with source_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError(f"Table {table_name!r} has no header row.")
        if table_cfg.source_column not in fieldnames:
            raise ValueError(
                f"Source column '{table_cfg.source_column}' absent from table {table_name!r}."
            )
        if table_cfg.embedding_column in fieldnames:
            raise ValueError(
                f"Embedding column '{table_cfg.embedding_column}' already present in table {table_name!r}."
            )
        rows: list[dict[str, str]] = []
        texts: list[str] = []
        for idx, row in enumerate(reader):
            if table_cfg.source_column not in row:
                raise ValueError(
                    f"Row {idx + 1} in table {table_name!r} lacks column '{table_cfg.source_column}'."
                )
            rows.append(row)
            texts.append(row[table_cfg.source_column] or "")

    embeddings: list[list[float]] = []
    model = table_cfg.model or default_model
    if rows:
        embeddings = _batch_embeddings(client=client, model=model, texts=texts, batch_size=batch_size)
        if len(embeddings) != len(rows):
            raise OpenAIBackendError(
                f"Embedding backend returned {len(embeddings)} vectors for {len(rows)} rows."
            )
    else:
        log.warning("Table %s is empty; embedding column will be added without rows.", table_name)

    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        newline="",
        encoding="utf-8",
        suffix=source_path.suffix,
        prefix=f"{table_name}_emb_",
    ) as tmp:
        writer = csv.DictWriter(
            tmp,
            fieldnames=[*fieldnames, table_cfg.embedding_column],
            delimiter=delimiter,
        )
        writer.writeheader()
        for idx, row in enumerate(rows):
            payload = dict(row)
            payload[table_cfg.embedding_column] = json.dumps(
                embeddings[idx],
                separators=(",", ":"),
            )
            writer.writerow(payload)
    tmp_path = Path(tmp.name)
    return tmp_path


def _batch_embeddings(
    *,
    client: OpenAICompatibleClient,
    model: str,
    texts: list[str],
    batch_size: int,
) -> list[list[float]]:
    results: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        log.debug(
            "Requesting embeddings chunk (model=%s, offset=%d, size=%d)",
            model,
            start,
            len(chunk),
        )
        vectors = client.embeddings(model=model, inputs=chunk)
        if len(vectors) != len(chunk):
            raise OpenAIBackendError(
                f"Embedding backend returned {len(vectors)} vectors for chunk of size {len(chunk)}."
            )
        results.extend(vectors)
    return results
