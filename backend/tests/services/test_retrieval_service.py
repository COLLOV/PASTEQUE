from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pytest

from insight_backend.core.config import settings
from insight_backend.services.retrieval_service import RetrievalAgent


class _StubMindsDBClient:
    def __init__(self, payloads: Dict[str, Dict[str, Any]], calls: List[str]):
        self._payloads = payloads
        self._calls = calls

    def sql(self, query: str) -> Dict[str, Any]:
        self._calls.append(query)
        lower = query.strip().lower()
        if "from " not in lower:
            raise AssertionError(f"Unexpected query: {query}")
        table = lower.rsplit("from ", 1)[-1].strip()
        payload = self._payloads.get(table)
        if payload is None:
            raise AssertionError(f"No payload configured for query: {query}")
        return payload

    def close(self) -> None:  # pragma: no cover - nothing to release
        return


class _StubEmbeddingClient:
    def __init__(self, vectors: Dict[str, List[float]], calls: List[Dict[str, Any]]):
        self._vectors = vectors
        self._calls = calls

    def embeddings(self, *, model: str, inputs: List[str]) -> List[List[float]]:
        self._calls.append({"model": model, "inputs": list(inputs)})
        vector = self._vectors.get(model)
        if vector is None:
            raise AssertionError(f"Unexpected embedding request for model={model}")
        return [list(vector)]

    def close(self) -> None:  # pragma: no cover - nothing to release
        return


@pytest.fixture(autouse=True)
def _reset_retrieval_cache() -> Iterable[None]:
    RetrievalAgent._cached_index = None  # type: ignore[attr-defined]
    RetrievalAgent._cached_signature = None  # type: ignore[attr-defined]
    yield
    RetrievalAgent._cached_index = None  # type: ignore[attr-defined]
    RetrievalAgent._cached_signature = None  # type: ignore[attr-defined]


def _write_table(path: Path, rows: List[Dict[str, Any]], *, fieldnames: List[str]) -> None:
    import csv

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _config_yaml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_retrieval_agent_returns_ranked_rows_and_caches_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    tickets_path = tables_dir / "tickets.csv"
    feedback_path = tables_dir / "feedback.csv"

    _write_table(
        tickets_path,
        [
            {"id": "A1", "description": "Laptop too slow"},
            {"id": "A2", "description": "Cannot print invoice"},
        ],
        fieldnames=["id", "description"],
    )
    _write_table(
        feedback_path,
        [
            {"id": "B1", "commentaire": "Agency response was helpful"},
            {"id": "B2", "commentaire": "Mobile app crashes"},
        ],
        fieldnames=["id", "commentaire"],
    )

def _setup_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[RetrievalAgent, List[str], List[Dict[str, Any]]]:
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    tickets_path = tables_dir / "tickets.csv"
    feedback_path = tables_dir / "feedback.csv"

    _write_table(
        tickets_path,
        [
            {"id": "A1", "description": "Laptop too slow"},
            {"id": "A2", "description": "Cannot print invoice"},
        ],
        fieldnames=["id", "description"],
    )
    _write_table(
        feedback_path,
        [
            {"id": "B1", "commentaire": "Agency response was helpful"},
            {"id": "B2", "commentaire": "Mobile app crashes"},
        ],
        fieldnames=["id", "commentaire"],
    )

    config_path = tmp_path / "embed.yaml"
    _config_yaml(
        config_path,
        "\n".join(
            [
                "default_model: default-model",
                "tables:",
                "  tickets:",
                "    source_column: description",
                "    embedding_column: description_embedding",
                "  feedback:",
                "    source_column: commentaire",
                "    embedding_column: commentaire_embedding",
                "    model: alt-model",
            ]
        ),
    )

    monkeypatch.setattr(settings, "tables_dir", str(tables_dir))
    monkeypatch.setattr(settings, "mindsdb_embeddings_config_path", str(config_path))
    monkeypatch.setattr(settings, "retrieval_top_k", 3)
    monkeypatch.setattr(settings, "nl2sql_db_prefix", "files")

    payloads = {
        "files.tickets": {
            "column_names": ["id", "description", "description_embedding"],
            "data": [
                ["A1", "Laptop too slow", json.dumps([0.9, 0.0])],
                ["A2", "Cannot print invoice", json.dumps([0.1, 0.9])],
            ],
        },
        "files.feedback": {
            "column_names": ["id", "commentaire", "commentaire_embedding"],
            "data": [
                ["B1", "Agency response was helpful", json.dumps([0.3, 0.7])],
                ["B2", "Mobile app crashes", json.dumps([0.0, 1.0])],
            ],
        },
    }
    mindsdb_queries: List[str] = []

    def mindsdb_factory() -> _StubMindsDBClient:
        return _StubMindsDBClient(payloads, mindsdb_queries)

    embedding_vectors = {
        "default-model": [0.8, 0.2],
        "alt-model": [0.0, 1.0],
    }
    embedding_calls: List[Dict[str, Any]] = []

    def embedding_factory() -> _StubEmbeddingClient:
        return _StubEmbeddingClient(embedding_vectors, embedding_calls)

    agent = RetrievalAgent(
        mindsdb_factory=mindsdb_factory,
        embedding_factory=embedding_factory,
    )
    return agent, mindsdb_queries, embedding_calls


def test_retrieval_agent_returns_ranked_rows_and_caches_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent, mindsdb_queries, embedding_calls = _setup_agent(tmp_path, monkeypatch)

    results = agent.retrieve(
        question="Comment accélérer le support ?",
        top_k=3,
        allowed_tables=None,
        excluded_tables=[],
    )
    assert [item.payload["id"] for item in results] == ["B2", "A1", "B1"]
    # Two queries (one per table) to build the index
    assert len(mindsdb_queries) == 2
    # Second call should reuse the cached index (no new SQL queries)
    mindsdb_queries_snapshot = list(mindsdb_queries)
    results_again = agent.retrieve(
        question="Comment accélérer le support ?",
        top_k=3,
        allowed_tables=None,
        excluded_tables=[],
    )
    assert [item.payload["id"] for item in results_again] == ["B2", "A1", "B1"]
    assert mindsdb_queries == mindsdb_queries_snapshot
    # Embeddings invoked per model on each retrieval call
    assert [call["model"] for call in embedding_calls] == ["default-model", "alt-model", "default-model", "alt-model"]


def test_retrieval_agent_respects_allowed_and_excluded_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent, mindsdb_queries, _ = _setup_agent(tmp_path, monkeypatch)

    only_tickets = agent.retrieve(
        question="PC lent",
        top_k=2,
        allowed_tables=["tickets"],
        excluded_tables=[],
    )
    assert [item.table for item in only_tickets] == ["tickets", "tickets"]

    skip_tickets = agent.retrieve(
        question="Application mobile",
        top_k=2,
        allowed_tables=None,
        excluded_tables=["tickets"],
    )
    assert [item.table for item in skip_tickets] == ["feedback", "feedback"]
    # Index built exactly once for both calls
    assert len(mindsdb_queries) == 2
