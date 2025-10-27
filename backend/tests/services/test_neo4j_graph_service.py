import json

from insight_backend.integrations.neo4j_client import Neo4jResult
from insight_backend.services.neo4j_graph_service import Neo4jGraphService


def _normalize(cypher: str) -> str:
    return Neo4jGraphService._normalize_date_literals(cypher)


def test_normalize_date_literal_in_comparison():
    query = "MATCH (t:Ticket) WHERE t.creation_date >= '2024-01-01' RETURN t"
    normalized = _normalize(query)
    assert "date('2024-01-01')" in normalized
    assert normalized.count("date('2024-01-01')") == 1


def test_normalize_date_literal_in_list():
    query = "MATCH (n:AppFeedback) WHERE n.date_feedback IN ['2024-01-01', 'N/A'] RETURN n"
    normalized = _normalize(query)
    assert "date('2024-01-01')" in normalized
    assert "'N/A'" in normalized


def test_normalize_datetime_literal_truncated_to_date():
    query = "MATCH (t:Ticket) WHERE t.creation_date = '2024-01-01T10:30:00' RETURN t"
    normalized = _normalize(query)
    assert "date('2024-01-01')" in normalized
    assert "2024-01-01T10:30:00" not in normalized


def test_keep_existing_date_function_untouched():
    query = "MATCH (t:Ticket) WHERE t.creation_date = date('2024-01-01') RETURN t"
    normalized = _normalize(query)
    assert normalized == query


def test_non_date_field_unchanged():
    query = "MATCH (t:Ticket) WHERE t.resume = '2024-01-01' RETURN t"
    normalized = _normalize(query)
    assert normalized == query
def test_result_snapshot_truncation():
    result = Neo4jResult(
        columns=["ticket_id"],
        rows=[{"ticket_id": f"T-{i}"} for i in range(25)],
        row_count=25,
    )
    snapshot = Neo4jGraphService._result_snapshot(result, max_rows=5)
    assert snapshot is not None
    payload = json.loads(snapshot)
    assert payload["row_count"] == 25
    assert payload["truncated"] is True
    assert len(payload["rows"]) == 5


def test_harmonize_answer_returns_original_when_same_query(monkeypatch):
    result = Neo4jResult(columns=["ticket_id"], rows=[{"ticket_id": "T-1"}], row_count=1)

    def fake_regenerate(**kwargs):
        raise AssertionError("should not be called")

    monkeypatch.setattr(Neo4jGraphService, "_regenerate_answer", staticmethod(fake_regenerate))

    harmonized = Neo4jGraphService._harmonize_answer(
        question="Combien de tickets ?",
        original_answer="Réponse initiale.",
        cypher="MATCH (t:Ticket) RETURN t",
        sanitized_cypher="MATCH (t:Ticket) RETURN t",
        result=result,
        model_name="test-model",
        provider=None,
    )
    assert harmonized == "Réponse initiale."


def test_harmonize_answer_uses_regenerated(monkeypatch):
    result = Neo4jResult(columns=["ticket_id"], rows=[{"ticket_id": "T-1"}], row_count=1)

    def fake_regenerate(**kwargs):
        return "Nouvelle réponse."

    monkeypatch.setattr(Neo4jGraphService, "_regenerate_answer", staticmethod(fake_regenerate))

    harmonized = Neo4jGraphService._harmonize_answer(
        question="Combien de tickets ?",
        original_answer="Réponse initiale.",
        cypher="MATCH (t:Ticket {creation_date: '2024-01-01'}) RETURN t",
        sanitized_cypher="MATCH (t:Ticket {creation_date: date('2024-01-01')}) RETURN t",
        result=result,
        model_name="test-model",
        provider=None,
    )
    assert harmonized == "Nouvelle réponse."
