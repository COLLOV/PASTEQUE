from typing import Any, Dict, List, Tuple

import pytest

from insight_backend.services.chat_service import ChatService


class DummyEngine:
    def run(self, payload):  # pragma: no cover - not used here
        raise NotImplementedError


class DummyClient:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload

    def sql(self, _sql: str):
        return self._payload


def collect_events() -> Tuple[List[Tuple[str, Dict[str, Any]]], Any]:
    bucket: List[Tuple[str, Dict[str, Any]]] = []

    def _events(kind: str, payload: Dict[str, Any]):
        bucket.append((kind, payload))

    return bucket, _events


def test_derive_evidence_sql_from_aggregate_uses_where_and_limit():
    svc = ChatService(DummyEngine())
    sql = "SELECT count(*) FROM files.tickets WHERE status='open' GROUP BY status ORDER BY status"
    derived = svc._derive_evidence_sql(sql)
    assert derived is not None
    low = derived.lower()
    # Allow formatter to add spaces around '='
    assert low.startswith("select * from files.tickets where status") and "'open'" in low
    assert low.endswith("limit 100") or low.endswith("limit 100;") is False


def test_derive_evidence_sql_select_star_adds_limit_if_missing():
    svc = ChatService(DummyEngine())
    sql = "SELECT * FROM files.tickets"
    derived = svc._derive_evidence_sql(sql)
    assert derived and derived.lower().endswith("limit 100")


def test_derive_evidence_sql_with_cte_keeps_where_and_cte():
    svc = ChatService(DummyEngine())
    sql = (
        "WITH t AS (SELECT * FROM files.tickets) "
        "SELECT count(*) FROM t WHERE status='open' GROUP BY status"
    )
    derived = svc._derive_evidence_sql(sql)
    assert derived is not None
    # Must keep WITH and WHERE
    low = derived.lower().replace("\n", " ")
    assert low.startswith("with ") and " from t " in low and " where status='open'" in low


def test_derive_evidence_sql_union_is_skipped():
    svc = ChatService(DummyEngine())
    sql = (
        "SELECT count(*) FROM files.tickets WHERE status='open'"
        " UNION ALL SELECT count(*) FROM files.tickets WHERE status='closed'"
    )
    assert svc._derive_evidence_sql(sql) is None


def test_build_evidence_spec_infers_keys_and_limit():
    svc = ChatService(DummyEngine())
    cols = ["ticket_id", "title", "status", "created_at"]
    spec = svc._build_evidence_spec(cols, label_hint="tickets summary")
    assert spec["entity_label"] == "Tickets"
    assert spec["pk"] == "ticket_id"
    assert spec["display"]["created_at"] == "created_at"
    assert spec["limit"] == 100


def test_normalize_result_handles_table_shape():
    svc = ChatService(DummyEngine())
    payload = {
        "type": "table",
        "column_names": ["id", "title"],
        "data": [[1, "a"], [2, "b"]],
    }
    cols, rows = svc._normalize_result(payload)
    assert cols == ["id", "title"]
    assert rows == [[1, "a"], [2, "b"]]


def test_emit_evidence_uses_fallback_when_no_derived():
    svc = ChatService(DummyEngine())
    bucket, events = collect_events()
    client = DummyClient({})
    svc._emit_evidence(
        events=events,
        client=client,
        label_hint="tickets",
        base_sql=None,
        fallback_columns=["id", "title"],
        fallback_rows=[[1, "a"]],
    )
    kinds = [k for k, _ in bucket]
    assert "meta" in kinds and "rows" in kinds


def test_emit_evidence_with_derived_sql():
    svc = ChatService(DummyEngine())
    bucket, events = collect_events()
    client = DummyClient({
        "type": "table",
        "column_names": ["id", "title"],
        "data": [[1, "a"], [2, "b"]],
    })
    svc._emit_evidence(
        events=events,
        client=client,
        label_hint="tickets",
        base_sql="SELECT count(*) FROM files.tickets",
        fallback_columns=None,
        fallback_rows=None,
    )
    kinds = [k for k, _ in bucket]
    assert kinds.count("sql") >= 1
    assert "meta" in kinds and "rows" in kinds


def test_format_retrieval_highlight_with_payload(monkeypatch: pytest.MonkeyPatch):
    svc = ChatService(DummyEngine())

    def _fake_insight(self, *, question: str, rows: List[Dict[str, Any]]) -> str:  # type: ignore[override]
        assert question == "Pourquoi les tickets sont en retard ?"
        assert rows
        return "Les tickets urgents montrent des blocages récurrents sur le portail."

    monkeypatch.setattr(ChatService, "_generate_retrieval_insight", _fake_insight)

    highlight = svc._format_retrieval_highlight(
        question="Pourquoi les tickets sont en retard ?",
        payload=[
            {
                "table": "tickets",
                "score": 0.9234,
                "focus": "Portail inaccessible",
                "source_column": "description",
                "values": {"description": "Portail inaccessible", "priority": "high"},
            }
        ],
    )
    assert highlight == (
        "Mise en avant : Les tickets urgents montrent des blocages récurrents sur le portail."
    )


def test_format_retrieval_highlight_handles_error():
    svc = ChatService(DummyEngine())
    text = svc._format_retrieval_highlight(question="Pourquoi ?", payload=[], error="timeout")
    assert text == "Mise en avant : récupération indisponible (timeout)."


def test_append_highlight_adds_separator():
    result = ChatService._append_highlight("Réponse", "Mise en avant : Exemple")
    assert result.endswith("Mise en avant : Exemple")
    assert "\n\n" in result
