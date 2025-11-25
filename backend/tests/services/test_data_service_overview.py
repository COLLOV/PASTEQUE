from insight_backend.repositories.data_repository import DataRepository
from insight_backend.services.data_service import DataService


def test_overview_includes_all_columns_and_detects_dates(tmp_path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    sample = tables_dir / "dataset.csv"
    sample.write_text(
        "\n".join(
            [
                "date_event,department,campaign",
                "2024-05-01,North,Alpha",
                "2024-05-02,South,Alpha",
                "2024-05-02,South,Beta",
                ",,",
            ]
        ),
        encoding="utf-8",
    )

    service = DataService(repo=DataRepository(tables_dir=tables_dir))
    overview = service.get_overview()

    assert overview.sources, "Aucune source détectée"
    source = overview.sources[0]
    assert source.total_rows == 4

    fields = {field.field: field for field in source.fields}
    assert set(fields) == {"date_event", "department", "campaign"}

    date_field = fields["date_event"]
    assert date_field.kind == "date"
    assert date_field.missing_values == 1
    assert [c.label for c in date_field.counts][-1] == "2024-05-02"

    dept_field = fields["department"]
    assert dept_field.unique_values == 2
    assert dept_field.counts[0].label == "South"
    assert dept_field.counts[0].count == 2
