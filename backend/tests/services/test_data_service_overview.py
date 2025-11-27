from insight_backend.repositories.data_repository import DataRepository
from insight_backend.services.data_service import DataService
from insight_backend.schemas.data import TableExplorePreview


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


def test_overview_includes_category_breakdown_when_available(tmp_path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    sample = tables_dir / "dataset.csv"
    sample.write_text(
        "\n".join(
            [
                "Category,Sub Category,value,date",
                "A,X,1,2024-01-01",
                "A,X,2,2024-01-02",
                "A,Y,3,2024-01-03",
                "B,X,4,",
                "B,Z,5,2024-01-02",
            ]
        ),
        encoding="utf-8",
    )

    service = DataService(repo=DataRepository(tables_dir=tables_dir))
    overview = service.get_overview()

    assert overview.sources, "Aucune source détectée"
    source = overview.sources[0]

    pairs = {(item.category, item.sub_category): item.count for item in source.category_breakdown}
    assert pairs == {
        ("A", "X"): 2,
        ("A", "Y"): 1,
        ("B", "X"): 1,
        ("B", "Z"): 1,
    }
    assert source.date_min == "2024-01-01"
    assert source.date_max == "2024-01-03"


def test_overview_filters_by_date_range(tmp_path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    sample = tables_dir / "dataset.csv"
    sample.write_text(
        "\n".join(
            [
                "Category,Sub Category,value,date",
                "A,X,1,2024-05-01",
                "A,X,2,2024-05-02",
                "A,Y,3,2024-05-03",
                "B,X,4,2024-05-04",
            ]
        ),
        encoding="utf-8",
    )

    service = DataService(repo=DataRepository(tables_dir=tables_dir))
    overview = service.get_overview(date_from="2024-05-02", date_to="2024-05-03")

    source = overview.sources[0]
    assert source.total_rows == 2
    pairs = {(item.category, item.sub_category): item.count for item in source.category_breakdown}
    assert pairs == {("A", "X"): 1, ("A", "Y"): 1}


def test_explore_table_filters_rows_by_category_and_sub_category(tmp_path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    sample = tables_dir / "dataset.csv"
    sample.write_text(
        "\n".join(
            [
                "Category,Sub Category,value,other",
                "A,X,1,a",
                "A,X,2,b",
                "A,Y,3,c",
                "B,X,4,d",
            ]
        ),
        encoding="utf-8",
    )

    service = DataService(repo=DataRepository(tables_dir=tables_dir))
    result: TableExplorePreview = service.explore_table(
        table_name="dataset",
        category="A",
        sub_category="X",
        limit=10,
    )

    assert result.source == "dataset"
    assert result.category == "A"
    assert result.sub_category == "X"
    assert result.matching_rows == 2
    assert len(result.preview_rows) == 2
    assert result.preview_columns == ["Category", "Sub Category", "value", "other"]
    for row in result.preview_rows:
        assert row["Category"] == "A"
        assert row["Sub Category"] == "X"


def test_explore_table_supports_pagination_and_date_sort(tmp_path):
    tables_dir = tmp_path / "tables"
    tables_dir.mkdir()

    sample = tables_dir / "dataset.csv"
    sample.write_text(
        "\n".join(
            [
                "Category,Sub Category,date,value",
                "A,X,2024-05-01,1",
                "A,X,2024-05-03,2",
                "A,X,2024-05-02,3",
                "A,Y,2024-05-04,9",
            ]
        ),
        encoding="utf-8",
    )

    service = DataService(repo=DataRepository(tables_dir=tables_dir))

    page_1 = service.explore_table(
        table_name="dataset",
        category="A",
        sub_category="X",
        limit=1,
        offset=0,
        sort_date="desc",
    )
    assert page_1.matching_rows == 3
    assert len(page_1.preview_rows) == 1
    assert page_1.preview_rows[0]["date"] == "2024-05-03"
    assert page_1.date_min == "2024-05-01"
    assert page_1.date_max == "2024-05-03"
    assert page_1.date_from is None
    assert page_1.date_to is None

    page_2 = service.explore_table(
        table_name="dataset",
        category="A",
        sub_category="X",
        limit=1,
        offset=1,
        sort_date="desc",
    )
    assert page_2.preview_rows[0]["date"] == "2024-05-02"

    asc_page = service.explore_table(
        table_name="dataset",
        category="A",
        sub_category="X",
        limit=2,
        offset=0,
        sort_date="asc",
    )
    assert [row["date"] for row in asc_page.preview_rows] == ["2024-05-01", "2024-05-02"]

    filtered = service.explore_table(
        table_name="dataset",
        category="A",
        sub_category="X",
        limit=5,
        offset=0,
        sort_date="asc",
        date_from="2024-05-02",
        date_to="2024-05-03",
    )
    assert filtered.matching_rows == 2
    assert [row["date"] for row in filtered.preview_rows] == ["2024-05-02", "2024-05-03"]
    assert filtered.date_from == "2024-05-02"
    assert filtered.date_to == "2024-05-03"
