from __future__ import annotations

import re

_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_title(s: str) -> str:
    """Return a safe, plain-text title string.

    - remove control characters
    - replace angle brackets
    - collapse whitespace
    - clamp length to 120 chars
    """
    s = _CTRL_RE.sub(" ", s)
    s = s.replace("<", " ").replace(">", " ")
    s = " ".join(s.split())
    s = s[:120] if len(s) > 120 else s
    return s or "Nouvelle conversation"

