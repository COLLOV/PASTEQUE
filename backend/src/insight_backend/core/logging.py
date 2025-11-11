import logging
from typing import Optional, Sequence, Tuple


DETAIL_LOGGERS: Sequence[str] = (
    "insight.core.agent_logs",
    "insight.services.chat",
    "insight.repositories.conversation",
    "httpx",
)


def _resolve_level(level: Optional[str]) -> Tuple[str, int]:
    if not level:
        from .config import settings  # Lazy import to avoid circular deps at module load time

        level = settings.log_level
    normalized = (level or "INFO").upper()
    return normalized, getattr(logging, normalized, logging.INFO)


def _apply_detail_overrides() -> None:
    try:
        from .config import settings
    except Exception:
        return

    detail_enabled = bool(settings.detailed_agent_logs)
    for name in DETAIL_LOGGERS:
        logger = logging.getLogger(name)
        target = logging.INFO if detail_enabled else logging.WARNING
        logger.setLevel(target)


def configure_logging(level: Optional[str] = None) -> None:
    root = logging.getLogger()
    already_configured = bool(root.handlers)
    if not already_configured:
        normalized, resolved_level = _resolve_level(level)
        logging.basicConfig(
            level=resolved_level,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        logging.getLogger("insight").info("Logging configured: level=%s", normalized)
    _apply_detail_overrides()
