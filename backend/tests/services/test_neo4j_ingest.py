from datetime import date, datetime

from insight_backend.services.neo4j_ingest import Neo4jIngestionService


def test_coerce_value_date():
    value = Neo4jIngestionService._coerce_value("created", "2025-03-01", ("created",))
    assert isinstance(value, date)
    assert value == date(2025, 3, 1)


def test_coerce_value_datetime():
    value = Neo4jIngestionService._coerce_value("created", "2025-03-01 11:22:18", ("created",))
    assert isinstance(value, datetime)
    assert value == datetime(2025, 3, 1, 11, 22, 18)


def test_coerce_value_invalid_keeps_string():
    value = Neo4jIngestionService._coerce_value("created", "invalid-date", ("created",))
    assert value == "invalid-date"


def test_prepare_props_skips_fields_and_applies_dates():
    row = {
        "ticket_id": "T-01",
        "creation_date": "2025-02-03",
        "other": " value ",
    }
    props = Neo4jIngestionService._prepare_props(
        row,
        date_fields=("creation_date",),
        skip_fields={"ticket_id"},
    )
    assert "ticket_id" not in props
    assert isinstance(props["creation_date"], date)
    assert props["other"] == "value"
