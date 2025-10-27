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


def test_summarize_result_scalar():
    result = Neo4jResult(columns=["total_tickets"], rows=[{"total_tickets": 500}], row_count=1)
    summary = Neo4jGraphService._summarize_result(result)
    assert "500" in summary
    assert "total tickets" in summary


def test_summarize_result_rows():
    result = Neo4jResult(
        columns=["ticket_id", "departement"],
        rows=[
            {"ticket_id": "T-1", "departement": "75"},
            {"ticket_id": "T-2", "departement": "69"},
        ],
        row_count=2,
    )
    summary = Neo4jGraphService._summarize_result(result)
    assert "2 enregistrement" in summary
    assert "ticket_id=T-1" in summary


def test_harmonize_answer_uses_summary_when_query_changes():
    result = Neo4jResult(
        columns=["ticket_id"],
        rows=[{"ticket_id": "T-1"}],
        row_count=1,
    )
    harmonized = Neo4jGraphService._harmonize_answer(
        question="Combien de tickets ?",
        original_answer="Aucun ticket trouvé.",
        cypher="MATCH (t:Ticket) RETURN t",
        sanitized_cypher="MATCH (t:Ticket) RETURN t",
        result=result,
    )
    # No change expected because cypher identical
    assert harmonized == "Aucun ticket trouvé."

    harmonized_changed = Neo4jGraphService._harmonize_answer(
        question="Combien de tickets ?",
        original_answer="Aucun ticket trouvé.",
        cypher="MATCH (t:Ticket {creation_date: '2024-01-01'}) RETURN t",
        sanitized_cypher="MATCH (t:Ticket {creation_date: date('2024-01-01')}) RETURN t",
        result=result,
    )
    assert harmonized_changed != "Aucun ticket trouvé."
    assert "1 enregistrement" in harmonized_changed or "renvoie" in harmonized_changed
