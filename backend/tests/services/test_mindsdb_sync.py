from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from insight_backend.core.config import settings
from insight_backend.services.mindsdb_sync import sync_all_tables


class _StubMindsDBClient:
    def __init__(self, *, uploads: list[str]):
        self._uploads = uploads

    def upload_file(self, path: str | Path) -> None:
        p = Path(path)
        self._uploads.append(p.read_text(encoding="utf-8"))

    def close(self) -> None:  # pragma: no cover - nothing to clean
        return


class _StubEmbeddingClient:
    def __init__(self, *, calls: list[dict[str, object]]):
        self._calls = calls
        self._offset = 0

    def embeddings(self, *, model: str, inputs: list[str]) -> list[list[float]]:
        self._calls.append({"model": model, "inputs": list(inputs)})
        start = self._offset
        self._offset += len(inputs)
        # Deterministic toy vectors with unique offsets
        return [[float(start + idx), float(start + idx) + 0.5] for idx in range(len(inputs))]

    def close(self) -> None:  # pragma: no cover - nothing to clean
        return


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure state isolation across tests."""
    monkeypatch.setattr(settings, "llm_mode", "api")
    monkeypatch.setattr(settings, "openai_base_url", "http://embedding.test")
    monkeypatch.setattr(settings, "openai_api_key", "dummy")
    monkeypatch.setattr(settings, "openai_timeout_s", 5)
    monkeypatch.setattr(settings, "mindsdb_base_url", "http://mindsdb.test")
    monkeypatch.setattr(settings, "mindsdb_token", "token")
    monkeypatch.setattr(settings, "embedding_model", None)


def test_sync_all_tables_adds_embedding_column(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    csv_path = tables_dir / "products.csv"
    csv_path.write_text("id,text\n1,hello\n2,world\n", encoding="utf-8")

    config_path = tmp_path / "embed.yaml"
    config_path.write_text(
        "\n".join(
            [
                "default_model: test-embed",
                "batch_size: 1",
                "tables:",
                "  products:",
                "    source_column: text",
                "    embedding_column: text_embedding",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "tables_dir", str(tables_dir))
    monkeypatch.setattr(settings, "mindsdb_embeddings_config_path", str(config_path))

    uploads: list[str] = []
    embedding_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "insight_backend.services.mindsdb_sync.MindsDBClient",
        lambda base_url, token: _StubMindsDBClient(uploads=uploads),
    )
    monkeypatch.setattr(
        "insight_backend.services.mindsdb_sync.OpenAICompatibleClient",
        lambda base_url, api_key, timeout_s: _StubEmbeddingClient(calls=embedding_calls),
    )

    uploaded = sync_all_tables()

    assert uploaded == ["products.csv"]
    assert len(embedding_calls) == 2  # two single-row batches (batch_size=1)
    assert all(call["model"] == "test-embed" for call in embedding_calls)

    assert len(uploads) == 1
    reader = csv.DictReader(io.StringIO(uploads[0]))
    assert reader.fieldnames == ["id", "text", "text_embedding"]
    rows = list(reader)
    assert len(rows) == 2
    assert json.loads(rows[0]["text_embedding"]) == [0.0, 0.5]
    assert json.loads(rows[1]["text_embedding"]) == [1.0, 1.5]


def test_sync_all_tables_missing_source_column_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    csv_path = tables_dir / "products.csv"
    csv_path.write_text("id,text\n1,hello\n", encoding="utf-8")

    config_path = tmp_path / "embed.yaml"
    config_path.write_text(
        "\n".join(
            [
                "tables:",
                "  products:",
                "    source_column: missing",
                "    embedding_column: text_embedding",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "tables_dir", str(tables_dir))
    monkeypatch.setattr(settings, "mindsdb_embeddings_config_path", str(config_path))

    monkeypatch.setattr(
        "insight_backend.services.mindsdb_sync.MindsDBClient",
        lambda base_url, token: _StubMindsDBClient(uploads=[]),
    )
    monkeypatch.setattr(
        "insight_backend.services.mindsdb_sync.OpenAICompatibleClient",
        lambda base_url, api_key, timeout_s: _StubEmbeddingClient(calls=[]),
    )

    with pytest.raises(ValueError, match="Source column 'missing' absent"):
        sync_all_tables()
