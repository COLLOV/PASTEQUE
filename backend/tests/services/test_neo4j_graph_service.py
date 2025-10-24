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
