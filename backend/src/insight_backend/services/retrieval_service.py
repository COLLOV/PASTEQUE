from __future__ import annotations

import heapq
import json
import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence

from ..core.config import settings
from ..integrations.mindsdb_client import MindsDBClient
from ..integrations.openai_client import OpenAIBackendError, OpenAICompatibleClient
from ..repositories.data_repository import DataRepository
from . import mindsdb_sync as _mindsdb_sync


log = logging.getLogger("insight.services.retrieval")


@dataclass(slots=True)
class _IndexedRow:
    table: str
    table_key: str
    model: str
    source_column: str
    source_text: str
    payload: Dict[str, Any]
    vector: tuple[float, ...]
    norm: float


@dataclass(slots=True)
class RetrievalResult:
    table: str
    score: float
    source_column: str
    source_text: str
    payload: Dict[str, Any]
    model: str


@dataclass(slots=True)
class _RetrievalIndex:
    rows_by_model: Dict[str, List[_IndexedRow]]
    signature: tuple[tuple[str, str, str, str, str], ...]

    @property
    def models(self) -> Iterable[str]:
        return self.rows_by_model.keys()

    def iter_rows(
        self,
        *,
        allowed: set[str] | None,
        excluded: set[str],
    ) -> Iterable[_IndexedRow]:
        for bucket in self.rows_by_model.values():
            for row in bucket:
                if allowed is not None and row.table_key not in allowed:
                    continue
                if row.table_key in excluded:
                    continue
                yield row


def _vector_norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))


def _ensure_float_vector(raw: Any) -> tuple[float, ...]:
    if raw is None:
        raise ValueError("Embedding payload is null.")
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, (list, tuple)):
        try:
            return tuple(float(x) for x in raw)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Embedding contains non-numeric values: {raw!r}") from exc
    raise ValueError(f"Unsupported embedding payload type: {type(raw)!r}")


def _cosine_similarity(
    a: Sequence[float],
    norm_a: float,
    b: Sequence[float],
    norm_b: float,
) -> float:
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (norm_a * norm_b)


class RetrievalAgent:
    """Vector search helper injecting data rows into chat context."""

    _cache_lock = threading.Lock()
    _cached_index: _RetrievalIndex | None = None
    _cached_signature: tuple[tuple[str, str, str, str, str], ...] | None = None

    def __init__(
        self,
        *,
        mindsdb_factory: Callable[[], MindsDBClient] | None = None,
        embedding_factory: Callable[[], OpenAICompatibleClient] | None = None,
    ):
        self._mindsdb_factory = mindsdb_factory or self._default_mindsdb_factory
        self._embedding_factory = embedding_factory or self._default_embedding_factory

    def retrieve(
        self,
        *,
        question: str,
        top_k: int,
        allowed_tables: Iterable[str] | None,
        excluded_tables: Iterable[str],
    ) -> List[RetrievalResult]:
        text = (question or "").strip()
        if not text:
            return []

        index = self._ensure_index()

        allowed = {name.casefold() for name in allowed_tables} if allowed_tables else None
        excluded = {name.casefold() for name in excluded_tables if isinstance(name, str)}

        embeddings_client = self._embedding_factory()
        try:
            query_vectors = self._embed_question(text, models=index.models, client=embeddings_client)
        finally:
            embeddings_client.close()

        if not query_vectors:
            return []

        limit = max(1, int(top_k))
        heap: list[tuple[float, int, RetrievalResult]] = []
        counter = 0

        for row in index.iter_rows(allowed=allowed, excluded=excluded):
            query = query_vectors.get(row.model)
            if query is None:
                continue
            vector, norm = query
            score = _cosine_similarity(row.vector, row.norm, vector, norm)
            if math.isnan(score):  # pragma: no cover - defensive
                continue
            counter += 1
            result = RetrievalResult(
                table=row.table,
                score=score,
                source_column=row.source_column,
                source_text=row.source_text,
                payload=dict(row.payload),
                model=row.model,
            )
            item = (score, counter, result)
            if len(heap) < limit:
                heapq.heappush(heap, item)
            else:
                if score > heap[0][0]:
                    heapq.heapreplace(heap, item)

        selected = [item[2] for item in heap]
        selected.sort(key=lambda r: r.score, reverse=True)
        log.info(
            "Retrieval agent matched %d rows (candidates=%d, top_k=%d, tables=%s)",
            len(selected),
            counter,
            limit,
            sorted({res.table for res in selected}),
        )
        return selected

    def _ensure_index(self) -> _RetrievalIndex:
        config = self._load_embedding_config()
        signature = self._compute_signature(config)
        with self._cache_lock:
            if self._cached_index and self._cached_signature == signature:
                return self._cached_index
            index = self._build_index(config, signature)
            self._cached_index = index
            self._cached_signature = signature
            return index

    def _build_index(
        self,
        config: _mindsdb_sync.EmbeddingConfig,
        signature: tuple[tuple[str, str, str, str, str], ...],
    ) -> _RetrievalIndex:
        client = self._mindsdb_factory()
        repo = DataRepository(tables_dir=Path(settings.tables_dir))
        try:
            rows_by_model: Dict[str, List[_IndexedRow]] = {}
            total_rows = 0
            for table_name, table_cfg in config.tables.items():
                prefix = settings.nl2sql_db_prefix
                sql = f"SELECT * FROM {prefix}.{table_name}"
                payload = client.sql(sql)
                _, raw_rows = self._normalize_rows(payload)
                if not raw_rows:
                    log.warning("Retrieval agent: table %s returned no rows from MindsDB.", table_name)
                    continue
                table_rows = 0
                for raw in raw_rows:
                    try:
                        vector = _ensure_float_vector(raw.get(table_cfg.embedding_column))
                    except ValueError as exc:
                        log.warning("Skipping row without valid embedding in %s: %s", table_name, exc)
                        continue
                    if len(vector) == 0:
                        continue
                    norm = _vector_norm(vector)
                    source_text = str(raw.get(table_cfg.source_column, "")).strip()
                    payload_row = {
                        key: value
                        for key, value in raw.items()
                        if key != table_cfg.embedding_column
                    }
                    indexed = _IndexedRow(
                        table=table_name,
                        table_key=table_name.casefold(),
                        model=table_cfg.model or config.default_model,
                        source_column=table_cfg.source_column,
                        source_text=source_text,
                        payload=payload_row,
                        vector=vector,
                        norm=norm,
                    )
                    rows_by_model.setdefault(indexed.model, []).append(indexed)
                    table_rows += 1
                total_rows += table_rows
                if table_rows == 0:
                    log.warning(
                        "Retrieval agent: table %s has no usable rows (embedding column %s).",
                        table_name,
                        table_cfg.embedding_column,
                    )
            if not total_rows:
                raise RuntimeError("Retrieval agent index is empty; ensure embeddings are populated in MindsDB.")
            log.info(
                "Retrieval agent index built: %d rows across %d tables (models=%s)",
                total_rows,
                len(config.tables),
                sorted(rows_by_model.keys()),
            )
            return _RetrievalIndex(rows_by_model=rows_by_model, signature=signature)
        finally:
            client.close()

    def _embed_question(
        self,
        question: str,
        models: Iterable[str],
        client: OpenAICompatibleClient,
    ) -> Dict[str, tuple[tuple[float, ...], float]]:
        vectors: Dict[str, tuple[tuple[float, ...], float]] = {}
        unique_models = list(dict.fromkeys(models))
        for model in unique_models:
            raw = client.embeddings(model=model, inputs=[question])
            if not raw:
                raise OpenAIBackendError(f"Embedding backend returned no vector for model {model}.")
            vector = _ensure_float_vector(raw[0])
            norm = _vector_norm(vector)
            if norm == 0.0:
                log.warning("Embedding for model %s has zero norm; skipping retrieval contribution.", model)
                continue
            vectors[model] = (vector, norm)
        return vectors

    def _load_embedding_config(self) -> _mindsdb_sync.EmbeddingConfig:
        config = _mindsdb_sync._load_embedding_config(settings.mindsdb_embeddings_config_path)
        if not config or not config.tables:
            raise RuntimeError(
                "Retrieval agent requires MINDSDB_EMBEDDINGS_CONFIG_PATH with at least one table."
            )
        return config

    def _compute_signature(
        self,
        config: _mindsdb_sync.EmbeddingConfig,
    ) -> tuple[tuple[str, str, str, str, str], ...]:
        repo = DataRepository(tables_dir=Path(settings.tables_dir))
        signature: List[tuple[str, str, str, str, str]] = []
        for table_name, cfg in config.tables.items():
            path = repo._resolve_table_path(table_name)
            if path is None:
                raise FileNotFoundError(f"Retrieval agent: table file not found: {table_name}")
            digest = _mindsdb_sync._compute_file_hash(path)
            model = cfg.model or config.default_model
            signature.append((table_name, digest, cfg.source_column, cfg.embedding_column, model))
        signature.sort()
        return tuple(signature)

    def _normalize_rows(
        self,
        payload: Dict[str, Any],
    ) -> tuple[List[str], List[Dict[str, Any]]]:
        columns: List[str] = []
        rows: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            columns = payload.get("column_names") or payload.get("columns") or []
            data = payload.get("data") or payload.get("rows") or []
            if isinstance(data, list):
                if data and isinstance(data[0], dict):
                    rows = [dict(item) for item in data]
                else:
                    rows = [dict(zip(columns, item)) for item in data]
        return columns, rows

    @staticmethod
    def _default_mindsdb_factory() -> MindsDBClient:
        return MindsDBClient(base_url=settings.mindsdb_base_url, token=settings.mindsdb_token)

    @staticmethod
    def _default_embedding_factory() -> OpenAICompatibleClient:
        mode = (settings.llm_mode or "").strip().lower()
        if mode == "local":
            base_url = settings.vllm_base_url
            api_key = None
        elif mode == "api":
            base_url = settings.openai_base_url
            api_key = settings.openai_api_key
        else:
            raise RuntimeError("LLM_MODE must be 'local' or 'api' for retrieval embeddings.")
        if not base_url:
            raise RuntimeError(f"Embedding backend base URL missing for LLM_MODE={settings.llm_mode!r}.")

        client = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            timeout_s=settings.openai_timeout_s,
        )
        log.info("Retrieval agent using embedding backend at %s (mode=%s)", base_url, mode)
        return client
