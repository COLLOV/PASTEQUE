from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import logging
import math
import time
from typing import Any, Dict, Iterable, List, Sequence

from ..repositories.data_repository import DataRepository


log = logging.getLogger("insight.services.rag")


@dataclass(slots=True)
class TicketRAGItem:
    ticket_id: str
    resume: str
    description: str
    departement: str | None
    creation_date: str | None
    score: float


@dataclass(slots=True)
class TicketRAGResult:
    items: List[TicketRAGItem]
    model: str
    top_k: int


class EmbeddingClientProtocol:
    def embeddings(self, *, model: str, inputs: Sequence[str]) -> Dict[str, Any]:  # pragma: no cover - protocol only
        raise NotImplementedError


class TicketRAGService:
    def __init__(
        self,
        *,
        repo: DataRepository,
        client: EmbeddingClientProtocol,
        store_path: Path,
        table_name: str,
        text_columns: Sequence[str],
        embedding_model: str,
        batch_size: int,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        self._repo = repo
        self._client = client
        self._store_path = store_path
        self._table_name = table_name
        self._text_columns = tuple(col.strip() for col in text_columns if col.strip())
        if not self._text_columns:
            raise ValueError("text_columns must contain at least one column name")
        self._embedding_model = embedding_model
        self._batch_size = batch_size
        self._cached_store: Dict[str, Any] | None = None
        self._cached_items: List[Dict[str, Any]] | None = None

    def retrieve(self, question: str, *, top_k: int) -> TicketRAGResult:
        if not question.strip():
            raise ValueError("question is empty")
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        store = self._ensure_store()
        items = self._cached_items or []
        if not items:
            raise RuntimeError("vector store is empty")
        query_embedding = self._embed_single(question)
        scored = self._score_items(query_embedding, items)
        limited = scored[: min(top_k, len(scored))]
        rag_items = [
            TicketRAGItem(
                ticket_id=item["metadata"].get("ticket_id", ""),
                resume=item["metadata"].get("resume", ""),
                description=item["metadata"].get("description", ""),
                departement=item["metadata"].get("departement"),
                creation_date=item["metadata"].get("creation_date"),
                score=item["score"],
            )
            for item in limited
        ]
        return TicketRAGResult(items=rag_items, model=store["model"], top_k=top_k)

    def _ensure_store(self) -> Dict[str, Any]:
        if self._cached_store is not None and self._cached_items is not None:
            return self._cached_store
        source_path = self._resolve_source_path()
        existing = self._repo.load_vector_store(str(self._store_path))
        if existing and self._is_store_valid(existing, source_path):
            self._cached_store = existing
            self._cached_items = [
                {
                    "embedding": item["embedding"],
                    "metadata": item["metadata"],
                }
                for item in existing.get("items", [])
            ]
            return existing
        log.info("Rebuilding ticket vector store (table=%s)", self._table_name)
        built = self._build_store(source_path)
        self._repo.save_vector_store(str(self._store_path), built)
        self._cached_store = built
        self._cached_items = [
            {
                "embedding": item["embedding"],
                "metadata": item["metadata"],
            }
            for item in built["items"]
        ]
        return built

    def _resolve_source_path(self) -> Path:
        path = self._repo._resolve_table_path(self._table_name)
        if path is None:
            raise FileNotFoundError(f"Table introuvable pour RAG: {self._table_name}")
        return path

    def _is_store_valid(self, store: Dict[str, Any], source_path: Path) -> bool:
        try:
            if store.get("model") != self._embedding_model:
                return False
            if tuple(store.get("text_columns") or ()) != self._text_columns:
                return False
            source_mtime = float(store.get("source_mtime", 0.0))
            if not math.isfinite(source_mtime):
                return False
            current_mtime = source_path.stat().st_mtime
            if current_mtime > source_mtime:
                return False
            items = store.get("items")
            if not isinstance(items, list) or not items:
                return False
            dimension = int(store.get("dimension", 0))
            if dimension <= 0:
                return False
            for item in items:
                embedding = item.get("embedding")
                if not isinstance(embedding, list) or len(embedding) != dimension:
                    return False
        except Exception:
            log.warning("Invalid vector store detected; forcing rebuild", exc_info=True)
            return False
        return True

    def _build_store(self, source_path: Path) -> Dict[str, Any]:
        rows = list(self._iter_source_rows(source_path))
        if not rows:
            raise RuntimeError("Ticket dataset is empty; cannot build vector store")
        texts = [self._compose_text(row) for row in rows]
        embeddings = self._embed_many(texts)
        if len(embeddings) != len(rows):
            raise RuntimeError("Embedding count mismatch")
        dimension = len(embeddings[0])
        items: List[Dict[str, Any]] = []
        for row, vector in zip(rows, embeddings):
            normalised = self._normalise(vector)
            item = {
                "metadata": row,
                "embedding": normalised,
            }
            items.append(item)
        store = {
            "table": self._table_name,
            "model": self._embedding_model,
            "dimension": dimension,
            "created_at": time.time(),
            "source_mtime": source_path.stat().st_mtime,
            "text_columns": list(self._text_columns),
            "items": items,
        }
        log.info("Ticket vector store built: %d items (dim=%d)", len(items), dimension)
        return store

    def _iter_source_rows(self, path: Path) -> Iterable[Dict[str, Any]]:
        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            for row in reader:
                if not row:
                    continue
                cleaned = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
                yield cleaned

    def _compose_text(self, row: Dict[str, Any]) -> str:
        parts: List[str] = []
        for col in self._text_columns:
            value = row.get(col, "")
            if value:
                parts.append(f"{col}: {value}")
        ticket_id = row.get("ticket_id")
        if ticket_id and ticket_id not in parts:
            parts.insert(0, f"ticket_id: {ticket_id}")
        return "\n".join(parts)

    def _embed_many(self, texts: Sequence[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for chunk in self._chunk(texts, self._batch_size):
            response = self._client.embeddings(model=self._embedding_model, inputs=chunk)
            data = response.get("data")
            if not isinstance(data, list) or len(data) != len(chunk):
                raise RuntimeError("Embedding backend returned unexpected payload")
            ordered = sorted(data, key=lambda item: item.get("index", 0))
            for payload in ordered:
                vector = payload.get("embedding")
                if not isinstance(vector, list):
                    raise RuntimeError("Missing embedding vector in response")
                vectors.append([float(v) for v in vector])
        return vectors

    def _embed_single(self, text: str) -> List[float]:
        response = self._client.embeddings(model=self._embedding_model, inputs=[text])
        data = response.get("data")
        if not isinstance(data, list) or len(data) != 1:
            raise RuntimeError("Embedding backend returned unexpected payload for single input")
        vector = data[0].get("embedding")
        if not isinstance(vector, list):
            raise RuntimeError("Missing embedding vector in response")
        return self._normalise([float(v) for v in vector])

    def _normalise(self, vector: Sequence[float]) -> List[float]:
        norm = math.sqrt(sum(v * v for v in vector))
        if norm <= 0 or not math.isfinite(norm):
            raise RuntimeError("Cannot normalise zero-length embedding")
        return [v / norm for v in vector]

    def _score_items(self, query: Sequence[float], items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scores: List[Dict[str, Any]] = []
        for entry in items:
            embedding = entry["embedding"]
            if len(embedding) != len(query):
                raise RuntimeError("Embedding dimension mismatch")
            score = sum(a * b for a, b in zip(query, embedding))
            scores.append({"metadata": entry["metadata"], "score": score})
        scores.sort(key=lambda item: item["score"], reverse=True)
        return scores

    def _chunk(self, seq: Sequence[str], size: int) -> Iterable[Sequence[str]]:
        for idx in range(0, len(seq), size):
            yield seq[idx : idx + size]
