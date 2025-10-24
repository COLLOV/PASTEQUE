from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
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
    _ensure_user_password_reset_column()
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


def _ensure_user_password_reset_column() -> None:
    """Ensure the must_reset_password column exists on the users table."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("users")}
        column_present = "must_reset_password" in columns
        added_column = False
        if not column_present:
            add_statement = text(
                "ALTER TABLE users ADD COLUMN "
                "must_reset_password BOOLEAN NOT NULL DEFAULT TRUE"
            )
            try:
                connection.execute(add_statement)
                column_present = True
                added_column = True
            except DBAPIError as exc:  # pragma: no cover - defensive guard
                if not _is_duplicate_column_error(exc):
                    raise
                column_present = True
        if column_present:
            connection.execute(
                text("UPDATE users SET must_reset_password = FALSE WHERE must_reset_password IS NULL")
            )
        if added_column:
            log.info("Added must_reset_password column to users table.")
        else:
            log.debug("must_reset_password column already present.")


def _is_duplicate_column_error(exc: DBAPIError) -> bool:
    """Return True if the DBAPIError indicates a duplicate column addition."""
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) == "42701":  # PostgreSQL duplicate column
        return True
    message = str(orig or exc).lower()
    return "duplicate column" in message and "must_reset_password" in message
