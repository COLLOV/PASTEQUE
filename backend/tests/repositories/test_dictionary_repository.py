import textwrap
from pathlib import Path

import pytest

from insight_backend.repositories.dictionary_repository import DataDictionaryRepository


def write_yaml(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_for_schema_filters_and_preserves_fields(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "foo.yml",
        """
        version: 1
        table: foo
        title: Foo Table
        description: Demo table
        columns:
          - name: A
            description: Alpha
            type: integer
            pii: false
          - name: b
            description: Beta
            type: string
            synonyms: [bee]
            unit: null
            pii: true
            example: "xyz"
          - name: C
            description: Should be filtered out
        """,
    )

    repo = DataDictionaryRepository(directory=tmp_path)
    schema = {"foo": ["A", "b", "does_not_exist"]}
    out = repo.for_schema(schema)

    assert set(out.keys()) == {"foo"}
    cols = out["foo"]["columns"]
    names = [c["name"] for c in cols]
    assert names == ["A", "b"]  # order preserved, missing filtered
    # field preservation
    field_b = next(c for c in cols if c["name"] == "b")
    assert field_b["pii"] is True
    assert field_b["synonyms"] == ["bee"]
    assert field_b["example"] == "xyz"


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    repo = DataDictionaryRepository(directory=tmp_path)
    out = repo.for_schema({"unknown": ["id"]})
    assert out == {}


def test_malformed_yaml_is_ignored(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "mal.yml",
        """
        version: 1
        table: mal
        columns: not-a-list
        """,
    )
    repo = DataDictionaryRepository(directory=tmp_path)
    out = repo.for_schema({"mal": ["id"]})
    # columns invalid → table ignored
    assert out == {}


def test_case_insensitive_column_match(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "t.yml",
        """
        version: 1
        table: t
        columns:
          - name: MixedCase
        """,
    )
    repo = DataDictionaryRepository(directory=tmp_path)
    out = repo.for_schema({"t": ["mixedcase"]})
    assert out["t"]["columns"][0]["name"] == "MixedCase"


def test_path_traversal_rejected(tmp_path: Path) -> None:
    # Name with traversal sequences is rejected
    repo = DataDictionaryRepository(directory=tmp_path)
    assert repo.load_table("../secret") is None
    assert repo.load_table("..\\secret") is None
