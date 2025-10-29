from __future__ import annotations

from pathlib import Path

from insight_backend.repositories.data_repository import DataRepository


def _write_csv(path: Path, header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        ",".join(header) + "\n",
        encoding="utf-8",
    )


def test_list_tables_across_multiple_directories(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _write_csv(raw_dir / "tickets.csv", ["ticket_id", "title"])
    _write_csv(processed_dir / "tickets_enriched.csv", ["ticket_id", "score"])

    repo = DataRepository(tables_dir=f"{raw_dir},{processed_dir}")

    tables = repo.list_tables()
    assert sorted(tables) == ["tickets", "tickets_enriched"]

    # La table processed doit être résolue correctement
    resolved = repo._resolve_table_path("tickets_enriched")
    assert resolved is not None
    assert resolved.samefile(processed_dir / "tickets_enriched.csv")


def test_resolve_table_name_with_extension(tmp_path: Path) -> None:
    base_dir = tmp_path / "data"
    _write_csv(base_dir / "dataset.tsv", ["id", "value"])

    repo = DataRepository(tables_dir=str(base_dir))

    resolved = repo._resolve_table_path("dataset.tsv")
    assert resolved is not None
    assert resolved.suffix == ".tsv"
