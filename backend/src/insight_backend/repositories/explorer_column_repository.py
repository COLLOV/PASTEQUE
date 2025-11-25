from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from ..models.explorer_hidden_column import ExplorerHiddenColumn


log = logging.getLogger("insight.repositories.explorer_columns")


class ExplorerColumnPreferenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_hidden_columns(self, table_name: str) -> list[str]:
        rows = (
            self.session.query(ExplorerHiddenColumn.column_name)
            .filter(ExplorerHiddenColumn.table_name == table_name)
            .all()
        )
        columns = [row[0] for row in rows]
        log.debug(
            "Loaded %d hidden columns for table=%s",
            len(columns),
            table_name,
        )
        return sorted(columns, key=lambda value: value.casefold())

    def get_hidden_columns_for_tables(self, table_names: Iterable[str]) -> dict[str, set[str]]:
        names = list(table_names)
        if not names:
            return {}
        rows = (
            self.session.query(ExplorerHiddenColumn.table_name, ExplorerHiddenColumn.column_name)
            .filter(ExplorerHiddenColumn.table_name.in_(names))
            .all()
        )
        mapping: dict[str, set[str]] = {}
        for table, column in rows:
            key = table
            columns = mapping.setdefault(key, set())
            columns.add(column)
        log.debug(
            "Loaded hidden columns overview for %d tables",
            len(mapping),
        )
        return mapping

    def set_hidden_columns(self, table_name: str, column_names: Iterable[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for name in column_names:
            cleaned = name.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)

        existing = (
            self.session.query(ExplorerHiddenColumn)
            .filter(ExplorerHiddenColumn.table_name == table_name)
            .all()
        )
        existing_map = {col.column_name.casefold(): col for col in existing}
        desired_keys = {name.casefold() for name in normalized}

        for key, entry in existing_map.items():
            if key not in desired_keys:
                self.session.delete(entry)
                log.info(
                    "Removed hidden explorer column table=%s column=%s",
                    table_name,
                    entry.column_name,
                )

        for name in normalized:
            key = name.casefold()
            if key in existing_map:
                continue
            entry = ExplorerHiddenColumn(table_name=table_name, column_name=name)
            self.session.add(entry)
            log.info(
                "Added hidden explorer column table=%s column=%s",
                table_name,
                name,
            )

        return sorted(normalized, key=lambda value: value.casefold())

