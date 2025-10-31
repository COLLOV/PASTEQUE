from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Generator, Dict
from pathlib import Path

from sqlalchemy import create_engine, inspect, text, event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from pgvector.psycopg import register_vector

from .config import settings


log = logging.getLogger("insight.core.database")


class Base(DeclarativeBase):
    """Base declarative class for SQLAlchemy models."""


engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect", once=False)
def _register_pgvector(dbapi_conn, _) -> None:  # pragma: no cover - relies on driver hooks
    try:
        register_vector(dbapi_conn)
    except Exception as exc:
        log.warning("Failed to register pgvector adapter: %s", exc)


def init_database() -> None:
    """Create schema if it does not exist."""
    # Import models so SQLAlchemy is aware of them before creating tables.
    from .. import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_conversation_indexes()
    _ensure_user_password_reset_column()
    _ensure_admin_column()
    _ensure_vector_schema()
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
    columns = {col["name"] for col in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "is_admin" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE users "
                    "ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
        previous_admins = conn.execute(
            text(
                "SELECT username FROM users "
                "WHERE is_admin = TRUE AND username <> :admin_username"
            ),
            {"admin_username": settings.admin_username},
        ).fetchall()
        if previous_admins:
            names = ", ".join(row[0] for row in previous_admins)
            log.warning("Resetting admin flag for unexpected users: %s", names)
        conn.execute(
            text(
                "UPDATE users "
                "SET is_admin = CASE WHEN username = :admin_username THEN TRUE ELSE FALSE END"
            ),
            {"admin_username": settings.admin_username},
        )
    log.info("Admin flag column ensured on users table.")


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


def _ensure_conversation_indexes() -> None:
    """Ensure helpful composite indexes exist for conversation items.

    Uses CREATE INDEX IF NOT EXISTS to avoid errors on repeated startups.
    """
    stmts = [
        "CREATE INDEX IF NOT EXISTS ix_conv_msg_conv_created ON conversation_messages (conversation_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_conv_evt_conv_created ON conversation_events (conversation_id, created_at)",
    ]
    with engine.begin() as conn:
        for sql in stmts:
            conn.execute(text(sql))
    log.info("Conversation composite indexes ensured.")


def discover_rag_tables() -> Dict[str, str]:
    """Return mapping of fully-qualified table name -> stem for data tables present in DB."""
    stems = _discover_data_table_stems()
    if not stems:
        return {}
    with engine.begin() as conn:
        mapping: dict[str, str] = {}
        for stem in stems:
            resolved = _resolve_table_for_stem(conn, stem)
            if resolved:
                mapping[resolved] = stem
            else:
                log.warning("Vector schema: table not found for stem '%s'", stem)
        return mapping


def ensure_vector_schema() -> None:
    """Public helper to ensure pgvector schema primitives exist."""
    _ensure_vector_schema()


def _discover_data_table_stems() -> list[str]:
    try:
        from ..repositories.data_repository import DataRepository
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Unable to import DataRepository for vector schema discovery: %s", exc)
        return []
    repo = DataRepository(Path(settings.tables_dir))
    try:
        return repo.list_tables()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Failed to list tables_dir '%s': %s", settings.tables_dir, exc)
        return []


def _resolve_table_for_stem(conn, stem: str) -> str | None:
    prefix = (settings.rag_table_prefix or "").strip()
    candidates = []
    if prefix:
        candidates.append(f"{prefix}{stem}")
    candidates.append(stem)
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        reg = conn.execute(text("SELECT to_regclass(:name)"), {"name": candidate}).scalar()
        if reg:
            return str(reg)
    return None


def _ensure_vector_schema() -> None:
    tables = discover_rag_tables()
    if not tables:
        log.info("No data tables discovered for pgvector setup; skipping.")
        return

    opclass = {
        "cosine": "vector_cosine_ops",
        "l2": "vector_l2_ops",
        "ip": "vector_ip_ops",
    }[settings.rag_distance]
    preparer = engine.dialect.identifier_preparer

    def _quote(name: str) -> str:
        parts = [p for p in name.split(".") if p]
        return ".".join(preparer.quote_identifier(part) for part in parts)

    def _index_name(table: str) -> str:
        base = table.replace(".", "_")
        return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in f"{base}_embedding_ivf")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        for qualified in tables:
            table_sql = _quote(qualified)
            try:
                conn.execute(
                    text(
                        f"ALTER TABLE {table_sql} "
                        f"ADD COLUMN IF NOT EXISTS embedding vector({settings.rag_embedding_dim})"
                    )
                )
            except Exception as exc:
                log.error("Failed to add embedding column on %s: %s", qualified, exc, exc_info=True)
                continue
            try:
                conn.execute(
                    text(
                        f"ALTER TABLE {table_sql} "
                        f"ALTER COLUMN embedding TYPE vector({settings.rag_embedding_dim})"
                    )
                )
            except Exception as exc:
                log.error(
                    "Failed to align embedding column dimension on %s: %s",
                    qualified,
                    exc,
                    exc_info=True,
                )
            index_name = _quote(_index_name(qualified))
            try:
                conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS {index_name} "
                        f"ON {table_sql} USING ivfflat (embedding {opclass}) "
                        f"WITH (lists={settings.rag_pgvector_lists})"
                    )
                )
            except Exception as exc:
                log.error("Failed to ensure ivfflat index on %s: %s", qualified, exc, exc_info=True)


def transactional(session: Session):
    """Return a context manager for an isolated write transaction.

    If a transaction is already open (often because a prior SELECT triggered
    autobegin), end it first so we can start a top-level `begin()` that will
    actually commit to the DB. This avoids nested transactions whose changes
    would be discarded if the outer transaction rolls back at request end.
    """
    if session.in_transaction():
        try:
            session.commit()  # safe even if only reads occurred
        except Exception:  # pragma: no cover - safety guard
            session.rollback()
    return session.begin()
