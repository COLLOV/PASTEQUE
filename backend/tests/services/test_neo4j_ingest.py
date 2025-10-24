from datetime import date

from insight_backend.services.neo4j_ingest import Neo4jIngestionService


def test_coerce_value_date_returns_date():
    value = Neo4jIngestionService._coerce_value("created", "2025-03-01", ("created",))
    assert isinstance(value, date)
    assert value == date(2025, 3, 1)


def test_coerce_value_datetime_string_normalised_to_date():
    value = Neo4jIngestionService._coerce_value("created", "2025-03-01 11:22:18", ("created",))
    assert isinstance(value, date)
    assert value == date(2025, 3, 1)


def test_coerce_value_integer():
    value = Neo4jIngestionService._coerce_value("amount", "42", tuple())
    assert isinstance(value, int)
    assert value == 42


def test_coerce_value_negative_integer():
    value = Neo4jIngestionService._coerce_value("delta", "-7", tuple())
    assert isinstance(value, int)
    assert value == -7


def test_coerce_value_non_numeric_remains_string():
    value = Neo4jIngestionService._coerce_value("note", "12.5", tuple())
    assert value == "12.5"


def test_prepare_props_skips_fields_and_trims():
    row = {
        "ticket_id": "T-01",
        "creation_date": "2025-02-03",
        "amount": " 123 ",
    }
    props = Neo4jIngestionService._prepare_props(
        row,
        date_fields=("creation_date",),
        skip_fields={"ticket_id"},
    )
    assert "ticket_id" not in props
    assert props["creation_date"] == date(2025, 2, 3)
    assert props["amount"] == 123
