from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import logging
import re
from typing import Iterable


log = logging.getLogger("insight.repositories.data")


@dataclass
class DataRepository:
    """Accès aux données (système de fichiers, S3, DB, etc.).

    Cette implémentation s'appuie sur des fichiers CSV/TSV dans `tables_dir`.
    """

    tables_dir: Path

    def __post_init__(self) -> None:
        self.tables_dir = Path(self.tables_dir)
        if not self.tables_dir.exists():
            log.warning("tables_dir inexistant: %s", self.tables_dir)

    # Vector store placeholders
    def save_vector_store(self, path: str) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    def load_vector_store(self, path: str) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    # CSV-backed tables
    def _iter_table_files(self) -> Iterable[Path]:
        if not self.tables_dir.exists():
            return []
        exts = {".csv", ".tsv"}
        files = [p for p in self.tables_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
        files.sort(key=lambda p: p.name.lower())
        return files

    def list_tables(self) -> list[str]:
        names = [p.stem for p in self._iter_table_files()]
        log.info("Tables découvertes (%d): %s", len(names), names)
        return names

    def _resolve_table_path(self, table_name: str) -> Path | None:
        candidates = [self.tables_dir / f"{table_name}.csv", self.tables_dir / f"{table_name}.tsv"]
        for c in candidates:
            if c.exists():
                return c
        # fallback strict: match by stem if user passed full filename without ext
        lookup = table_name.casefold()
        canonical = self.canonical_table_name(table_name)
        for p in self._iter_table_files():
            if (
                p.stem == table_name
                or p.stem.casefold() == lookup
                or self.canonical_table_name(p.stem) == canonical
            ):
                return p
        return None

    @staticmethod
    def canonical_table_name(name: str) -> str:
        """Canonical MindsDB identifier derived from the raw filename stem."""
        cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", name).strip("_")
        cleaned = re.sub(r"_+", "_", cleaned)
        if not cleaned:
            cleaned = "table"
        return cleaned.lower()

    def get_schema(self, table_name: str) -> list[tuple[str, str | None]]:
        path = self._resolve_table_path(table_name)
        if path is None:
            raise FileNotFoundError(f"Table introuvable: {table_name}")

        delimiter = "," if path.suffix.lower() == ".csv" else "\t"
        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)
            try:
                header = next(reader)
            except StopIteration:
                header = []

        cols = [(h, None) for h in header]
        log.info("Schéma table '%s' (%d colonnes)", table_name, len(cols))
        return cols
