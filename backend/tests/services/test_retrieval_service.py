from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import pytest

from insight_backend.core.config import settings
from insight_backend.services.mindsdb_embeddings import EmbeddingConfig, EmbeddingTableConfig
from insight_backend.services.retrieval_service import RetrievalService, SimilarRow


class _StubEmbeddingClient:
    def __init__(self, vectors: list[list[float]]):
        self._vectors = vectors
        self.closed = False

    def embeddings(self, *, model: str, inputs: list[str]) -> list[list[float]]:
        return self._vectors[: len(inputs)]

    def close(self) -> None:
        self.closed = True


class _StubMindsDBClient:
    def __init__(self, payload: dict[str, Any]):
        self._payload = payload
        self.closed = False

    def sql(self, query: str) -> dict[str, Any]:
        return self._payload

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mindsdb_base_url", "http://mindsdb.test")
    monkeypatch.setattr(settings, "mindsdb_token", "token")
    monkeypatch.setattr(settings, "nl2sql_db_prefix", "files")
    monkeypatch.setattr(settings, "rag_top_n", 2)
    monkeypatch.setattr(settings, "rag_table_row_cap", 10)
    monkeypatch.setattr(settings, "rag_max_columns", 3)


def test_retrieval_service_ranks_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = EmbeddingConfig(
        tables={
            "tickets": EmbeddingTableConfig(
                source_column="description",
                embedding_column="description_embedding",
                model=None,
            )
        },
        default_model="test-embed",
        batch_size=4,
    )
    monkeypatch.setattr(
        "insight_backend.services.retrieval_service.load_embedding_config",
        lambda path: config,
    )
    stub_client = _StubEmbeddingClient([[1.0, 0.0]])
    monkeypatch.setattr(
        "insight_backend.services.retrieval_service.build_embedding_client",
        lambda cfg: (stub_client, cfg.default_model),
    )
    minds_payload = {
        "type": "table",
        "column_names": ["id", "description", "priority", "description_embedding"],
        "data": [
            [1, "Le portail est inaccessible", "high", json.dumps([1.0, 0.0])],
            [2, "Connexion lente au portail client", "medium", json.dumps([0.8, 0.2])],
            [3, "Question FAQ", "low", json.dumps([0.0, 1.0])],
        ],
    }
    stub_minds = _StubMindsDBClient(minds_payload)
    monkeypatch.setattr(
        "insight_backend.services.retrieval_service.MindsDBClient",
        lambda base_url, token: stub_minds,
    )

    service = RetrievalService()
    rows = service.retrieve(question="Problèmes d'accès au portail", top_n=2)

    assert isinstance(rows, list)
    assert [row.focus for row in rows] == [
        "Le portail est inaccessible",
        "Connexion lente au portail client",
    ]
    assert all(isinstance(row, SimilarRow) for row in rows)
    assert rows[0].values["priority"] == "high"
    # capping columns (id, description, priority)
    assert len(rows[0].values) == 3
    assert stub_client.closed
    assert stub_minds.closed


def test_retrieval_service_without_config_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "insight_backend.services.retrieval_service.load_embedding_config",
        lambda path: None,
    )
    service = RetrievalService()
    with pytest.raises(RuntimeError):
        service.retrieve(question="test")
