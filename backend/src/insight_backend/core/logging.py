import logging
from typing import Optional, Tuple


def _resolve_level(level: Optional[str]) -> Tuple[str, int]:
    if not level:
        from .config import settings  # Lazy import to avoid circular deps at module load time

        level = settings.log_level
    normalized = (level or "INFO").upper()
    return normalized, getattr(logging, normalized, logging.INFO)


def configure_logging(level: Optional[str] = None) -> None:
    if logging.getLogger().handlers:
        return
    normalized, resolved_level = _resolve_level(level)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("insight").info("Logging configured: level=%s", normalized)
