import logging
import os


def configure_logging(level: str = "INFO") -> None:
    """Initialize or update the root logger with our canonical format."""
    desired_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(desired_level)
        for handler in root.handlers:
            handler.setLevel(desired_level)
        return
    logging.basicConfig(
        level=desired_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("insight").info("Logging configured: level=%s", level)


if os.getenv("ENV", "development") == "development":
    configure_logging()
