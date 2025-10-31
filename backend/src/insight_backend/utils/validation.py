from __future__ import annotations

from typing import Iterable

from ..core.config import settings


def normalize_table_names(
    tables: Iterable[object],
    *,
    max_items: int | None = None,
    max_len: int | None = None,
) -> list[str]:
    """Normalize a list of table names:

    - cast to string, strip, truncate
    - deduplicate case-insensitively preserving first-seen casing
    - cap list length
    """
    cap = settings.max_excluded_tables if max_items is None else max_items
    limit = settings.max_table_name_length if max_len is None else max_len
    out: list[str] = []
    seen: set[str] = set()
    count = 0
    for item in tables:
        if count >= cap:
            break
        if not isinstance(item, str):
            continue
        cleaned = item.strip()[: limit]
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        count += 1
    return out

