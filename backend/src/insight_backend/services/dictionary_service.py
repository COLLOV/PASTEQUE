from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Dict, Any

from ..repositories.data_repository import DataRepository
from ..repositories.dictionary_repository import DataDictionaryRepository
from ..schemas.dictionary import DictionaryTable, DictionaryColumn, DictionaryTableSummary
from ..core.config import settings


log = logging.getLogger("insight.services.dictionary")


ALLOWED_COLUMN_KEYS = {
    "name",
    "description",
    "type",
    "synonyms",
    "unit",
    "example",
    "pii",
    "nullable",
    "enum",
}


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _clean_str_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    out = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out.append(s)
    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for v in out:
        key = v.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(v)
    return deduped


def _clean_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        val = value.strip().lower()
        if val in {"true", "1", "yes", "y"}:
            return True
        if val in {"false", "0", "no", "n"}:
            return False
    return None


class DictionaryService:
    """Gestion des dictionnaires de données (YAML sur disque)."""

    def __init__(
        self,
        data_repo: DataRepository | None = None,
        dictionary_repo: DataDictionaryRepository | None = None,
    ):
        self.data_repo = data_repo or DataRepository(tables_dir=Path(settings.tables_dir))
        self.dictionary_repo = dictionary_repo or DataDictionaryRepository(
            directory=Path(settings.data_dictionary_dir)
        )

    def _schema_columns(self, table: str) -> list[str]:
        cols = [name for name, _ in self.data_repo.get_schema(table)]
        return cols

    def list_tables(self) -> list[DictionaryTableSummary]:
        names = self.data_repo.list_tables()
        summaries: list[DictionaryTableSummary] = []
        for name in names:
            try:
                cols = self._schema_columns(name)
            except FileNotFoundError:
                log.warning("Table introuvable lors du listing dictionnaire: %s", name)
                continue
            has_dict = self.dictionary_repo.load_table(name) is not None
            summaries.append(
                DictionaryTableSummary(
                    table=name,
                    has_dictionary=has_dict,
                    columns_count=len(cols),
                )
            )
        return summaries

    def get_table(self, table: str) -> DictionaryTable:
        columns = self._schema_columns(table)
        existing = self.dictionary_repo.load_table(table) or {}
        raw_cols = existing.get("columns") or []
        existing_lookup: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw_cols, list):
            for item in raw_cols:
                if not isinstance(item, dict):
                    continue
                name = _clean_str(item.get("name"))
                if not name:
                    continue
                existing_lookup[name.casefold()] = item
        parsed_columns: list[DictionaryColumn] = []
        for name in columns:
            base = existing_lookup.get(name.casefold()) or {}
            synonyms = _clean_str_list(base.get("synonyms"))
            enum_vals = _clean_str_list(base.get("enum"))
            parsed_columns.append(
                DictionaryColumn(
                    name=name,
                    description=_clean_str(base.get("description")),
                    type=_clean_str(base.get("type")),
                    synonyms=synonyms,
                    unit=_clean_str(base.get("unit")),
                    example=base.get("example"),
                    pii=_clean_bool(base.get("pii")),
                    nullable=_clean_bool(base.get("nullable")),
                    enum=enum_vals or None,
                )
            )
        return DictionaryTable(
            table=table,
            title=_clean_str(existing.get("title")),
            description=_clean_str(existing.get("description")),
            columns=parsed_columns,
        )

    def upsert_table(self, payload: DictionaryTable) -> DictionaryTable:
        table = payload.table.strip()
        if not table:
            raise ValueError("Le nom de table est requis.")
        schema_columns = self._schema_columns(table)
        allowed = {name.casefold(): name for name in schema_columns}
        existing = self.dictionary_repo.load_table(table) or {}
        existing_cols = existing.get("columns") or []
        existing_lookup: Dict[str, Dict[str, Any]] = {}
        if isinstance(existing_cols, list):
            for item in existing_cols:
                if not isinstance(item, dict):
                    continue
                name = _clean_str(item.get("name"))
                if not name:
                    continue
                normalized: Dict[str, Any] = {"name": name}
                for key in ALLOWED_COLUMN_KEYS:
                    if key == "name" or key not in item:
                        continue
                    raw_val = item.get(key)
                    if key in {"description", "type", "unit"}:
                        raw_val = _clean_str(raw_val)
                    elif key in {"synonyms", "enum"}:
                        raw_val = _clean_str_list(raw_val)
                    elif key in {"pii", "nullable"}:
                        raw_val = _clean_bool(raw_val)
                    if key in {"synonyms", "enum"}:
                        if raw_val:
                            normalized[key] = raw_val
                    elif key in {"pii", "nullable"}:
                        if raw_val is not None:
                            normalized[key] = raw_val
                    else:
                        if raw_val is not None:
                            normalized[key] = raw_val
                existing_lookup[name.casefold()] = normalized

        incoming_lookup: Dict[str, DictionaryColumn] = {}
        for col in payload.columns:
            name = col.name.strip()
            if not name:
                raise ValueError("Chaque colonne doit avoir un nom.")
            norm = name.casefold()
            if norm in incoming_lookup:
                raise ValueError(f"Colonne dupliquée: {name}")
            if norm not in allowed:
                raise ValueError(f"Colonne inconnue pour la table '{table}': {name}")
            incoming_lookup[norm] = col

        final_columns: list[Dict[str, Any]] = []
        for name in schema_columns:
            norm = name.casefold()
            base = dict(existing_lookup.get(norm, {}))
            base["name"] = name
            incoming = incoming_lookup.get(norm)
            if incoming:
                # Keep only explicitly provided fields to avoid overwriting existing metadata unintentionnally
                incoming_data = incoming.model_dump(exclude_unset=True)
                for key, value in incoming_data.items():
                    if key == "name":
                        continue
                    if key in {"description", "type", "unit"}:
                        value = _clean_str(value)
                    elif key in {"synonyms", "enum"}:
                        value = _clean_str_list(value)
                    elif key in {"pii", "nullable"}:
                        value = _clean_bool(value)
                    else:
                        # example or other allowed keys
                        pass
                    base[key] = value
            # Ensure ordering of keys and strip empty lists / None values except booleans
            cleaned: Dict[str, Any] = {"name": name}
            for key in ["description", "type", "synonyms", "unit", "example", "pii", "nullable", "enum"]:
                val = base.get(key)
                if key in {"synonyms", "enum"}:
                    if val:
                        cleaned[key] = list(val)
                elif key in {"pii", "nullable"}:
                    if val is not None:
                        cleaned[key] = bool(val)
                else:
                    if val is not None:
                        cleaned[key] = val
            final_columns.append(cleaned)

        payload_dict: Dict[str, Any] = {
            "version": existing.get("version", 1),
            "table": table,
            "columns": final_columns,
        }
        title = _clean_str(payload.title)
        description = _clean_str(payload.description)
        if title:
            payload_dict["title"] = title
        if description:
            payload_dict["description"] = description

        self.dictionary_repo.save_table(table, payload_dict)
        log.info("Dictionary updated for table=%s (columns=%d)", table, len(final_columns))
        # Reload to return normalized content
        return self.get_table(table)

    def delete_table(self, table: str) -> None:
        removed = self.dictionary_repo.delete_table(table)
        if not removed:
            raise FileNotFoundError(f"Aucun dictionnaire à supprimer pour '{table}'")
