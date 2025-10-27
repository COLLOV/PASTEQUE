from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from ..core.config import settings


def _storage_root() -> Path:
    """Return the chart storage directory, ensuring it exists."""
    root = Path(settings.mcp_chart_storage_path).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def chart_storage_root() -> Path:
    """Expose the resolved storage root (mostly for tests)."""
    return _storage_root()


def _path_candidates(raw: str) -> Iterable[Path]:
    """Yield possible filesystem mappings for the raw MCP response."""
    if not raw:
        return []

    parsed = urlparse(raw)
    candidates: list[Path] = []

    if parsed.scheme in ("http", "https"):
        if parsed.path:
            candidates.append(Path(parsed.path))
            candidates.append(Path(parsed.path.lstrip("/")))
    else:
        candidates.append(Path(raw))
        if raw.startswith("/"):
            candidates.append(Path(raw.lstrip("/")))

    # Always try filename fallback
    for candidate in list(candidates):
        if candidate.name:
            candidates.append(Path(candidate.name))

    return candidates


def resolve_chart_location(raw: str) -> Path:
    """
    Resolve the MCP returned location (path or URL) to a file within the storage root.

    Raises FileNotFoundError if the file cannot be resolved inside the storage root.
    Raises PermissionError if the resolved path escapes the storage directory.
    """
    root = _storage_root()
    normalized = None

    # First pass: direct candidates
    for candidate in _path_candidates(raw):
        base = candidate if candidate.is_absolute() else root / candidate
        resolved = base.expanduser().resolve()
        if resolved.exists():
            normalized = resolved
            break

    if normalized is None:
        raise FileNotFoundError(f"Chart image not found for location: {raw}")

    if not str(normalized).startswith(str(root)):
        raise PermissionError(f"Resolved chart path escapes storage root: {normalized}")

    return normalized


def to_relative_path(path: Path) -> str:
    """Convert an absolute chart path to a storage-root relative POSIX string."""
    root = _storage_root()
    resolved = path.expanduser().resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError(f"Path {resolved} is outside of chart storage root {root}")
    relative = resolved.relative_to(root)
    return relative.as_posix()


def to_absolute_path(relative: str) -> Path:
    """Convert a storage-root relative path to an absolute path."""
    root = _storage_root()
    candidate = (root / Path(relative)).expanduser().resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError(f"Relative chart path escapes storage root: {relative}")
    return candidate


def encode_chart_path(relative: str) -> str:
    """Encode a storage relative path into a URL-safe token."""
    data = relative.encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii")


def decode_chart_token(token: str) -> str:
    """Decode a chart path token back to its storage relative path."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError("Invalid chart token") from exc
    # Validate round-trip
    to_absolute_path(decoded)
    return decoded


def build_chart_view_url(relative: str) -> str:
    """Return the API route that serves the chart image."""
    token = encode_chart_path(relative)
    return f"{settings.api_prefix}/v1/mcp/chart/image/{token}"


def build_chart_preview_data_uri(relative: str) -> str | None:
    """Return a base64 data URI for thumbnail display, if the file exists."""
    path = to_absolute_path(relative)
    if not path.exists():
        return None
    mime, _ = mimetypes.guess_type(path.name)
    mime_type = mime or "image/png"
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
