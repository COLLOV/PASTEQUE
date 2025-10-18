import logging
import os


def configure_logging(level: str = "INFO") -> None:
    if logging.getLogger().handlers:
        return  # already configured
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Example minimal log to confirm boot
    logging.getLogger("insight").info("Logging configured: level=%s", level)


if os.getenv("ENV", "development") == "development":
    configure_logging()

