from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from insight_backend.core import database as db
from insight_backend.core.config import settings
from insight_backend.models.user import User


def test_ensure_admin_column_sets_only_configured_user_as_admin(monkeypatch):
    # Use isolated in-memory SQLite engine and tables
    engine = create_engine("sqlite:///:memory:")
    db.Base.metadata.create_all(bind=engine)

    # Patch the database module's engine used by _ensure_admin_column
    monkeypatch.setattr(db, "engine", engine, raising=True)

    with Session(bind=engine) as session:
        root = User(username="root", password_hash="x", is_active=True, is_admin=False)
        alice = User(username="alice", password_hash="x", is_active=True, is_admin=True)
        session.add_all([root, alice])
        session.commit()

    # Point the configured admin to 'root' for this test
    old_admin = settings.admin_username
    settings.admin_username = "root"
    try:
        db._ensure_admin_column()
    finally:
        settings.admin_username = old_admin

    with Session(bind=engine) as session:
        rows = session.scalars(select(User)).all()
        mapping = {u.username: u.is_admin for u in rows}
        assert mapping["root"] is True
        assert mapping["alice"] is False

