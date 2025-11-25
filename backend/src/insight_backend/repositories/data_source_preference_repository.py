from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.orm import Session

from ..models.data_source_preference import DataSourcePreference


log = logging.getLogger("insight.repositories.data_source_preference")


class DataSourcePreferenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_hidden_fields_by_source(self) -> dict[str, list[str]]:
        preferences = self.session.query(DataSourcePreference).all()
        result: dict[str, list[str]] = {}
        for pref in preferences:
            hidden: list[str] = []
            seen: set[str] = set()
            for name in pref.hidden_fields or []:
                if not isinstance(name, str):
                    continue
                trimmed = name.strip()
                if not trimmed:
                    continue
                key = trimmed.casefold()
                if key in seen:
                    continue
                seen.add(key)
                hidden.append(trimmed)
            if hidden:
                result[pref.source] = hidden
        log.debug("Loaded hidden fields for %d sources", len(result))
        return result

    def set_hidden_fields(self, *, source: str, hidden_fields: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for name in hidden_fields:
            if not isinstance(name, str):
                continue
            trimmed = name.strip()
            if not trimmed:
                continue
            key = trimmed.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(trimmed)

        pref = (
            self.session.query(DataSourcePreference)
            .filter(DataSourcePreference.source == source)
            .one_or_none()
        )
        if pref is None:
            pref = DataSourcePreference(source=source, hidden_fields=cleaned)
            self.session.add(pref)
        else:
            pref.hidden_fields = cleaned

        log.info("Updated hidden fields for source=%s (count=%d)", source, len(cleaned))
        return cleaned
