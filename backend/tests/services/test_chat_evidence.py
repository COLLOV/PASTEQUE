import pytest

from typing import Any, Dict, List, Tuple

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
    assert derived.lower().startswith("select * from files.tickets where status='open'")
    assert derived.lower().endswith("limit 100") or derived.lower().endswith("limit 100;") is False


def test_derive_evidence_sql_select_star_adds_limit_if_missing():
    svc = ChatService(DummyEngine())
    sql = "SELECT * FROM files.tickets"
    derived = svc._derive_evidence_sql(sql)
    assert derived and derived.lower().endswith("limit 100")


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

