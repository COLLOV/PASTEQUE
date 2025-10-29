from __future__ import annotations

from typing import Any


def normalize_rows(columns: list[Any] | None, rows: list[Any] | None) -> list[dict[str, Any]]:
    """Normalize tabular data into a list of dict rows keyed by column name.

    Accepts rows as list-of-dicts, list-of-arrays or scalars. Scalars are mapped to the
    first column name when available, or to key "value" otherwise.
    """
    cols = [str(c) for c in (columns or [])]
    norm: list[dict[str, Any]] = []
    if not rows:
        return norm
    for r in rows:
        if isinstance(r, dict):
            norm.append({k: r.get(k) for k in cols} if cols else dict(r))
        elif isinstance(r, (list, tuple)):
            obj: dict[str, Any] = {}
            for i, c in enumerate(cols):
                obj[c] = r[i] if i < len(r) else None
            norm.append(obj)
        else:
            key = cols[0] if cols else "value"
            norm.append({key: r})
    return norm

