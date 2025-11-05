import pytest

from insight_backend.services.mcp_chart_service import (
    ChartGenerationError,
    ChartGenerationService,
)


def test_constrain_rows_respects_byte_cap(monkeypatch):
    rows = [{"value": "x" * 2000} for _ in range(5)]

    monkeypatch.setattr(ChartGenerationService, "_MAX_SERIALIZED_PAYLOAD_BYTES", 10_000)

    limited, truncated_by_count, truncated_by_bytes, payload = ChartGenerationService._constrain_rows_for_llm(rows)

    assert truncated_by_bytes is True
    assert truncated_by_count is False
    assert len(limited) < len(rows)
    assert payload <= max(ChartGenerationService._MAX_SERIALIZED_PAYLOAD_BYTES - 4096, 1024)


def test_constrain_rows_respects_row_cap(monkeypatch):
    rows = [{"value": idx} for idx in range(6)]

    monkeypatch.setattr(ChartGenerationService, "_DEFAULT_MAX_ROWS", 3)
    monkeypatch.setattr(ChartGenerationService, "_MAX_SERIALIZED_PAYLOAD_BYTES", 100_000)

    limited, truncated_by_count, truncated_by_bytes, payload = ChartGenerationService._constrain_rows_for_llm(rows)

    assert truncated_by_count is True
    assert truncated_by_bytes is False
    assert len(limited) == 3
    assert limited == rows[:3]
    assert payload > 0


def test_constrain_rows_raises_when_single_row_too_large(monkeypatch):
    rows = [{"value": "y" * 2000}]

    monkeypatch.setattr(ChartGenerationService, "_MAX_SERIALIZED_PAYLOAD_BYTES", 5_000)

    with pytest.raises(ChartGenerationError):
        ChartGenerationService._constrain_rows_for_llm(rows)
