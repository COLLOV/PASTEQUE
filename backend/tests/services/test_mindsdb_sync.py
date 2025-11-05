from __future__ import annotations

import csv
import io
import json
import sys
import types
from pathlib import Path

import pytest

from insight_backend.core.config import settings
from insight_backend.services.mindsdb_sync import sync_all_tables
from insight_backend.services.mindsdb_embeddings import (
    build_embedding_client,
    default_embedding_model,
    EmbeddingConfig,
    EmbeddingTableConfig,
)


class _StubMindsDBClient:
    def __init__(self, *, uploads: list[tuple[str | None, str]]):
        self._uploads = uploads

    def upload_file(self, path: str | Path, *, table_name: str | None = None) -> None:
        p = Path(path)
        self._uploads.append((table_name, p.read_text(encoding="utf-8")))

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
    monkeypatch.setattr(settings, "embedding_mode", "api")
    monkeypatch.setattr(settings, "openai_base_url", "http://embedding.test")
    monkeypatch.setattr(settings, "openai_api_key", "dummy")
    monkeypatch.setattr(settings, "openai_timeout_s", 5)
    monkeypatch.setattr(settings, "mindsdb_base_url", "http://mindsdb.test")
    monkeypatch.setattr(settings, "mindsdb_token", "token")
    monkeypatch.setattr(settings, "embedding_model", None)


def test_build_embedding_client_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "embedding_mode", "local")
    monkeypatch.setattr(settings, "embedding_local_model", "hf-test-model")
    monkeypatch.setattr(settings, "embedding_model", None)

    resolved_default = default_embedding_model("config-embed-model")
    assert resolved_default == "hf-test-model"
    config = EmbeddingConfig(
        tables={
            "dummy": EmbeddingTableConfig(
                source_column="text",
                embedding_column="embedding",
                model=None,
            )
        },
        default_model=resolved_default,
        batch_size=2,
    )

    class _StubSentenceTransformer:
        def __init__(self, model_name: str):
            self._model_name = model_name

        def encode(
            self,
            inputs: list[str],
            *,
            convert_to_numpy: bool = True,
            show_progress_bar: bool = False,
        ) -> list[list[float]]:
            return [[float(idx), float(idx) + 0.5] for idx, _ in enumerate(inputs)]

    fake_module = types.SimpleNamespace(SentenceTransformer=_StubSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    client, model = build_embedding_client(config)
    try:
        vectors = client.embeddings(model=model, inputs=["foo", "bar"])
    finally:
        client.close()

    assert model == "hf-test-model"
    assert vectors == [[0.0, 0.5], [1.0, 1.5]]


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

    uploads: list[tuple[str | None, str]] = []
    embedding_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "insight_backend.services.mindsdb_sync.MindsDBClient",
        lambda base_url, token: _StubMindsDBClient(uploads=uploads),
    )
    monkeypatch.setattr(
        "insight_backend.services.mindsdb_embeddings.OpenAICompatibleClient",
        lambda base_url, api_key, timeout_s: _StubEmbeddingClient(calls=embedding_calls),
    )

    uploaded = sync_all_tables()

    assert uploaded == ["products.csv"]
    assert len(embedding_calls) == 2  # two single-row batches (batch_size=1)
    assert all(call["model"] == "test-embed" for call in embedding_calls)

    assert len(uploads) == 1
    table_name, payload = uploads[0]
    assert table_name == "products"
    reader = csv.DictReader(io.StringIO(payload))
    assert reader.fieldnames == ["id", "text", "text_embedding"]
    rows = list(reader)
    assert len(rows) == 2
    assert json.loads(rows[0]["text_embedding"]) == [0.0, 0.5]
    assert json.loads(rows[1]["text_embedding"]) == [1.0, 1.5]

    state_path = tables_dir / ".mindsdb_sync_state.json"
    assert state_path.exists()
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_data["products"]["embedding"]["model"] == "test-embed"


def test_sync_all_tables_skips_when_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()
    csv_path = tables_dir / "products.csv"
    csv_path.write_text("id,text\n1,hello\n2,world\n", encoding="utf-8")

    config_path = tmp_path / "embed.yaml"
    config_path.write_text(
        "\n".join(
            [
                "default_model: test-embed",
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

    uploads: list[tuple[str | None, str]] = []
    embedding_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "insight_backend.services.mindsdb_sync.MindsDBClient",
        lambda base_url, token: _StubMindsDBClient(uploads=uploads),
    )
    monkeypatch.setattr(
        "insight_backend.services.mindsdb_embeddings.OpenAICompatibleClient",
        lambda base_url, api_key, timeout_s: _StubEmbeddingClient(calls=embedding_calls),
    )

    first_run = sync_all_tables()
    assert first_run == ["products.csv"]
    assert uploads  # at least one upload
    assert embedding_calls

    # Reset collectors for second run
    second_uploads: list[tuple[str | None, str]] = []
    second_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "insight_backend.services.mindsdb_sync.MindsDBClient",
        lambda base_url, token: _StubMindsDBClient(uploads=second_uploads),
        raising=True,
    )
    monkeypatch.setattr(
        "insight_backend.services.mindsdb_embeddings.OpenAICompatibleClient",
        lambda base_url, api_key, timeout_s: _StubEmbeddingClient(calls=second_calls),
        raising=True,
    )

    second_run = sync_all_tables()
    assert second_run == []
    assert second_uploads == []
    assert second_calls == []


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
        "insight_backend.services.mindsdb_embeddings.OpenAICompatibleClient",
        lambda base_url, api_key, timeout_s: _StubEmbeddingClient(calls=[]),
    )

    with pytest.raises(ValueError, match="Source column 'missing' absent"):
        sync_all_tables()
