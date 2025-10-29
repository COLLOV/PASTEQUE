from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import logging
import os
import re
from typing import Iterable, Tuple


log = logging.getLogger("insight.repositories.data")


@dataclass
class DataRepository:
    """Accès aux données (système de fichiers, S3, DB, etc.).

    Cette implémentation s'appuie sur des fichiers CSV/TSV dans un ou
    plusieurs répertoires `tables_dir`.
    """

    tables_dir: Path | str

    def __post_init__(self) -> None:
        raw_dirs = self._parse_directories(self.tables_dir)
        object.__setattr__(self, "_tables_dirs", tuple(raw_dirs))
        # Conserver l'attribut historique `tables_dir` pour compatibilité
        if raw_dirs:
            object.__setattr__(self, "tables_dir", raw_dirs[0])
        else:
            fallback = Path(self.tables_dir) if not isinstance(self.tables_dir, Path) else self.tables_dir
            object.__setattr__(self, "tables_dir", fallback)
            log.warning("tables_dir non configuré, valeur brute=%s", self.tables_dir)

        for directory in raw_dirs:
            if not directory.exists():
                log.warning("tables_dir inexistant: %s", directory)

    @staticmethod
    def _parse_directories(raw: Path | str) -> list[Path]:
        if isinstance(raw, Path):
            raw_value = str(raw)
        else:
            raw_value = raw

        if not raw_value:
            return []

        # Supporter les séparateurs `,`, `;` et les retours à la ligne. On
        # évite `:` pour rester compatible Windows (C:\\...).
        chunks = re.split(r"[\n;,]", raw_value)
        dirs: list[Path] = []
        for chunk in chunks:
            cleaned = chunk.strip()
            if not cleaned:
                continue
            # Étendre l'alias PATH séparateur (utile si l'env utilise os.pathsep)
            subparts = cleaned.split(os.pathsep) if os.pathsep in cleaned else [cleaned]
            for part in subparts:
                normalized = part.strip()
                if not normalized:
                    continue
                dirs.append(Path(normalized))
        return dirs

    @property
    def tables_dirs(self) -> Tuple[Path, ...]:
        return getattr(self, "_tables_dirs", tuple())

    # Vector store placeholders
    def save_vector_store(self, path: str) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    def load_vector_store(self, path: str) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    # CSV-backed tables
    def _iter_table_files(self) -> Iterable[Path]:
        exts = {".csv", ".tsv"}
        mapping: dict[str, Path] = {}
        for directory in self.tables_dirs:
            if not directory.exists():
                continue
            for entry in directory.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in exts:
                    continue
                key = entry.stem.casefold()
                if key in mapping:
                    continue
                mapping[key] = entry
        files = [mapping[name] for name in sorted(mapping.keys())]
        return files

    def list_tables(self) -> list[str]:
        names = [p.stem for p in self._iter_table_files()]
        log.info("Tables découvertes (%d): %s", len(names), names)
        return names

    def _resolve_table_path(self, table_name: str) -> Path | None:
        candidates: list[Path] = []
        # Rechercher via nom simple
        for directory in self.tables_dirs:
            candidates.append(directory / f"{table_name}.csv")
            candidates.append(directory / f"{table_name}.tsv")
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Gestion des noms passés avec extension ou chemins relatifs
        as_path = Path(table_name)
        if as_path.suffix:
            for directory in self.tables_dirs:
                candidate = directory / as_path.name
                if candidate.exists():
                    return candidate

        # fallback strict: match par stem (sensible à la casse) sur l'ensemble
        stem_lookup = {p.stem: p for p in self._iter_table_files()}
        if table_name in stem_lookup:
            return stem_lookup[table_name]
        # version insensible à la casse
        lower_lookup = {p.stem.casefold(): p for p in self._iter_table_files()}
        match = lower_lookup.get(table_name.casefold())
        if match:
            return match
        return None

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
