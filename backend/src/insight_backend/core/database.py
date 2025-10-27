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


TABLE_PREFIX = "pasteque_"
USERS_TABLE = f"{TABLE_PREFIX}users"
CHARTS_TABLE = f"{TABLE_PREFIX}charts"
USER_TABLE_PERMISSIONS_TABLE = f"{TABLE_PREFIX}user_table_permissions"

LEGACY_TABLE_NAMES = {
    "users": USERS_TABLE,
    "charts": CHARTS_TABLE,
    "user_table_permissions": USER_TABLE_PERMISSIONS_TABLE,
}


engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_database() -> None:
    """Create schema if it does not exist."""
    # Import models so SQLAlchemy is aware of them before creating tables.
    from .. import models  # noqa: F401

    _rename_legacy_tables()
    Base.metadata.create_all(bind=engine)
    _ensure_user_password_reset_column()
    _ensure_admin_column()
    log.info("Database initialized (tables ensured).")


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _ensure_admin_column() -> None:
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns(USERS_TABLE)}
    with engine.begin() as conn:
        if "is_admin" not in columns:
            conn.execute(
                text(
                    f"ALTER TABLE {USERS_TABLE} "
                    "ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        previous_admins = conn.execute(
            text(
                f"SELECT username FROM {USERS_TABLE} "
                "WHERE is_admin = TRUE AND username <> :admin_username"
            ),
            {"admin_username": settings.admin_username},
        ).fetchall()
        if previous_admins:
            names = ", ".join(row[0] for row in previous_admins)
            log.warning("Resetting admin flag for unexpected users: %s", names)
        conn.execute(
            text(
                f"UPDATE {USERS_TABLE} "
                "SET is_admin = CASE WHEN username = :admin_username THEN TRUE ELSE FALSE END"
            ),
            {"admin_username": settings.admin_username},
        )
    log.info("Admin flag column ensured on %s table.", USERS_TABLE)


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
        columns = {column["name"] for column in inspector.get_columns(USERS_TABLE)}
        column_present = "must_reset_password" in columns
        added_column = False
        if not column_present:
            add_statement = text(
                f"ALTER TABLE {USERS_TABLE} ADD COLUMN "
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
                text(
                    f"UPDATE {USERS_TABLE} "
                    "SET must_reset_password = FALSE WHERE must_reset_password IS NULL"
                )
            )
        if added_column:
            log.info("Added must_reset_password column to %s.", USERS_TABLE)
        else:
            log.debug("must_reset_password column already present.")


def _is_duplicate_column_error(exc: DBAPIError) -> bool:
    """Return True if the DBAPIError indicates a duplicate column addition."""
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) == "42701":  # PostgreSQL duplicate column
        return True
    message = str(orig or exc).lower()
    return "duplicate column" in message and "must_reset_password" in message


def _rename_legacy_tables() -> None:
    """Rename tables from legacy names to prefixed variants to preserve data."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    pending = [
        (legacy, prefixed)
        for legacy, prefixed in LEGACY_TABLE_NAMES.items()
        if legacy in existing_tables and prefixed not in existing_tables
    ]
    if not pending:
        return
    with engine.begin() as connection:
        for legacy, prefixed in pending:
            connection.execute(text(f"ALTER TABLE {legacy} RENAME TO {prefixed}"))
            log.info("Renamed legacy table %s to %s", legacy, prefixed)
