from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from .config import settings


log = logging.getLogger("insight.core.database")


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""


engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_database() -> None:
    """Create schema if it does not exist."""
    # Import models so SQLAlchemy is aware of them before creating tables.
    from .. import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_user_dashboard_preference()
    log.info("Database initialized (tables ensured).")


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for manual session usage (startup tasks)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_user_dashboard_preference() -> None:
    """Ensure the dashboard visibility preference column exists."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "show_dashboard_charts" in columns:
            return
        connection.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN show_dashboard_charts BOOLEAN NOT NULL DEFAULT TRUE"
            )
        )
        log.info("Column users.show_dashboard_charts added with default TRUE.")
