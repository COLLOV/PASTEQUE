from __future__ import annotations

import csv
import json
import logging
import shutil
import tempfile
import hashlib
from pathlib import Path
from typing import Callable

from tqdm import tqdm

from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..integrations.openai_client import OpenAIBackendError
from ..repositories.data_repository import DataRepository
from .mindsdb_embeddings import (
    EmbeddingConfig,
    EmbeddingTableConfig,
    EmbeddingClient,
    build_embedding_client,
    load_embedding_config,
)


log = logging.getLogger("insight.services.mindsdb_sync")

STATE_FILENAME = ".mindsdb_sync_state.json"
CACHE_DIR_NAME = ".mindsdb_cache"


def sync_all_tables() -> list[str]:
    repo = DataRepository(tables_dir=Path(settings.tables_dir))
    files = list(repo._iter_table_files())
    if not files:
        log.info("No tables found in %s", repo.tables_dir)
        return []

    config = load_embedding_config(settings.mindsdb_embeddings_config_path)
    state_path = _state_path(repo.tables_dir)
    previous_state = _load_state(state_path)
    next_state: dict[str, dict[str, object]] = {}

    embedding_client: EmbeddingClient | None = None
    embedding_default_model: str | None = None
    if config and config.tables:
        available = {p.stem for p in files}
        missing = sorted(set(config.tables.keys()) - available)
        if missing:
            raise FileNotFoundError(
                f"MindsDB embedding configuration references missing tables: {', '.join(missing)}"
            )
        embedding_client, embedding_default_model = build_embedding_client(config)

    client = MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)
    uploaded: list[str] = []
    try:
        for path in files:
            table_name = path.stem
            table_cfg = config.tables.get(table_name) if config else None
            source_hash = _compute_file_hash(path)
            embedding_signature: dict[str, object] | None = None
            if table_cfg and embedding_default_model:
                resolved_model = table_cfg.model or embedding_default_model
                embedding_signature = {
                    "model": resolved_model,
                    "source_column": table_cfg.source_column,
                    "embedding_column": table_cfg.embedding_column,
                }
            previous_entry = previous_state.get(table_name) if previous_state else None
            # Skip only when unchanged AND the table already exists remotely. MindsDB container
            # is recreated at each start in dev, so we must re-upload when absent remotely
            # even if the local cache matches.
            cache_is_valid = (
                previous_entry
                and previous_entry.get("source_hash") == source_hash
                and previous_entry.get("embedding") == embedding_signature
            )
            if cache_is_valid:
                if _remote_table_exists(client, table_name):
                    log.info("Skipping %s (cached, unchanged, present remotely)", table_name)
                    next_state[table_name] = previous_entry
                    continue
                else:
                    log.info("Re-uploading %s (absent in MindsDB, cache intact)", table_name)

            tmp_path: Path | None = None
            try:
                if table_cfg:
                    if embedding_client is None or embedding_default_model is None:
                        raise RuntimeError("Embedding client not initialised.")

                    # Check if we have a cached file with embeddings
                    cached_path = _cached_file_path(repo.tables_dir, table_name, source_hash, path.suffix)

                    if cache_is_valid and cached_path.exists():
                        # Reuse cached file with embeddings (avoid recomputing)
                        upload_source = cached_path
                        log.info(
                            "Uploading %s with embeddings from cache (model=%s)",
                            table_name,
                            embedding_signature["model"] if embedding_signature else None,
                        )
                    else:
                        # Compute embeddings and cache the result
                        tmp_path = _augment_with_embeddings(
                            source_path=path,
                            table_name=table_name,
                            table_cfg=table_cfg,
                            client=embedding_client,
                            default_model=embedding_default_model,
                            batch_size=config.batch_size,
                        )
                        # Save to cache
                        cache_dir = _cache_dir_path(repo.tables_dir)
                        cache_dir.mkdir(exist_ok=True)
                        # Copy tmp file to cache (keep tmp_path for cleanup)
                        shutil.copy2(tmp_path, cached_path)
                        log.info(
                            "Cached embeddings for %s at %s",
                            table_name,
                            cached_path.relative_to(repo.tables_dir),
                        )
                        # Clean up old cache files
                        _cleanup_old_cache_files(repo.tables_dir, table_name, source_hash, path.suffix)

                        upload_source = tmp_path
                        log.info(
                            "Uploading %s with fresh embeddings (%s → %s, model=%s)",
                            table_name,
                            table_cfg.source_column,
                            table_cfg.embedding_column,
                            embedding_signature["model"] if embedding_signature else None,
                        )
                else:
                    upload_source = path
                    log.info("Uploading %s without embeddings", table_name)
                client.upload_file(upload_source, table_name=table_name)
                uploaded.append(path.name)
                next_state[table_name] = {
                    "source_hash": source_hash,
                    "embedding": embedding_signature,
                }
            finally:
                if tmp_path:
                    tmp_path.unlink(missing_ok=True)
    finally:
        client.close()
        if embedding_client:
            embedding_client.close()

    _save_state(state_path, next_state)

    log.info("Uploaded %d tables to MindsDB", len(uploaded))
    return uploaded


def _augment_with_embeddings(
    *,
    source_path: Path,
    table_name: str,
    table_cfg: EmbeddingTableConfig,
    client: EmbeddingClient,
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
        desc = f"Embeddings {table_name}"
        with tqdm(total=len(rows), desc=desc, unit="row", leave=False) as progress:
            embeddings = _batch_embeddings(
                client=client,
                model=model,
                texts=texts,
                batch_size=batch_size,
                progress_callback=progress.update,
            )
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
    progress_callback: Callable[[int], None] | None = None,
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
        if progress_callback:
            progress_callback(len(chunk))
    return results


def _compute_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state_path(tables_dir: Path) -> Path:
    return tables_dir / STATE_FILENAME


def _load_state(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Failed to load MindsDB sync state %s: %s (resetting cache)", path, exc)
        return {}


def _save_state(path: Path, state: dict[str, dict[str, object]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Failed to persist MindsDB sync state %s: %s", path, exc)


def _remote_table_exists(client: MindsDBClient, table_name: str) -> bool:
    """Best-effort check that ``files.table_name`` exists on MindsDB.

    - Returns True when the table appears queryable.
    - Returns False on any error (missing table, cold start), prompting a fresh upload.
    """
    db_prefix = settings.nl2sql_db_prefix or "files"
    # Some tests stub the client without a ``sql`` method; consider it present to avoid breaking tests
    if not hasattr(client, "sql"):
        return True
    try:
        result = client.sql(f"SELECT 1 FROM {db_prefix}.{table_name} LIMIT 1")
        # Check if the result indicates an error (MindsDB returns {'type': 'error', ...})
        if isinstance(result, dict) and result.get("type") == "error":
            return False
        return True
    except Exception:
        return False


def _cache_dir_path(tables_dir: Path) -> Path:
    """Return the path to the embeddings cache directory."""
    return tables_dir / CACHE_DIR_NAME


def _cached_file_path(tables_dir: Path, table_name: str, source_hash: str, suffix: str) -> Path:
    """Return the path to a cached file with embeddings."""
    cache_dir = _cache_dir_path(tables_dir)
    return cache_dir / f"{table_name}_{source_hash}{suffix}"


def _cleanup_old_cache_files(tables_dir: Path, table_name: str, current_hash: str, suffix: str) -> None:
    """Remove old cached embedding files for a table (with different hash)."""
    cache_dir = _cache_dir_path(tables_dir)
    if not cache_dir.exists():
        return

    pattern = f"{table_name}_*{suffix}"
    current_file = f"{table_name}_{current_hash}{suffix}"

    for cached_file in cache_dir.glob(pattern):
        if cached_file.name != current_file:
            try:
                cached_file.unlink()
                log.debug("Removed old cache file: %s", cached_file.name)
            except Exception as exc:
                log.warning("Failed to remove old cache file %s: %s", cached_file, exc)
