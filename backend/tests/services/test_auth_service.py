import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from insight_backend.core import database
from insight_backend.core.config import settings
from insight_backend.core.database import Base
from insight_backend.core.security import hash_password, user_is_admin
from insight_backend.models.user import User
from insight_backend.repositories.user_repository import UserRepository
from insight_backend.services.auth_service import AuthService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        with Session() as session:
            yield session
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_authenticate_requires_password_reset(session):
    repo = UserRepository(session)
    repo.create_user(
        username="alice",
        password_hash=hash_password("temp-password"),
        must_reset_password=True,
    )
    session.commit()

    service = AuthService(repo)

    with pytest.raises(HTTPException) as exc:
        service.authenticate(username="alice", password="temp-password")

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("code") == "PASSWORD_RESET_REQUIRED"


def test_reset_password_allows_authentication(session):
    repo = UserRepository(session)
    repo.create_user(
        username="bob",
        password_hash=hash_password("initial"),
        must_reset_password=True,
    )
    session.commit()

    service = AuthService(repo)
    service.reset_password(username="bob", current_password="initial", new_password="fresh-pass")
    session.commit()

    user, _ = service.authenticate(username="bob", password="fresh-pass")
    assert user.username == "bob"
    assert user.must_reset_password is False


def test_user_is_admin_requires_matching_username():
    user = User(
        username="not-admin",
        password_hash="hash",
        is_active=True,
        is_admin=True,
        must_reset_password=False,
    )
    assert not user_is_admin(user)


def test_user_is_admin_requires_admin_flag():
    user = User(
        username=settings.admin_username,
        password_hash="hash",
        is_active=True,
        is_admin=False,
        must_reset_password=False,
    )
    assert not user_is_admin(user)


def test_user_is_admin_accepts_only_configured_admin():
    user = User(
        username=settings.admin_username,
        password_hash="hash",
        is_active=True,
        is_admin=True,
        must_reset_password=False,
    )
    assert user_is_admin(user) is True


def test_ensure_admin_column_sets_only_configured_admin(monkeypatch, caplog):
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", Session)

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {database.USERS_TABLE} "
                    "(username, password_hash, is_active, is_admin, must_reset_password) "
                    "VALUES (:username, :password_hash, :is_active, :is_admin, :must_reset_password)"
                ),
                [
                    {
                        "username": settings.admin_username,
                        "password_hash": "hash",
                        "is_active": True,
                        "is_admin": False,
                        "must_reset_password": False,
                    },
                    {
                        "username": "rogue",
                        "password_hash": "hash",
                        "is_active": True,
                        "is_admin": True,
                        "must_reset_password": False,
                    },
                ],
            )

        caplog.clear()
        with caplog.at_level("WARNING"):
            database._ensure_admin_column()

        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT username, is_admin FROM {database.USERS_TABLE}")
            ).fetchall()
        states = {row[0]: bool(row[1]) for row in rows}

        assert states[settings.admin_username] is True
        assert states["rogue"] is False
        assert "Resetting admin flag for unexpected users: rogue" in caplog.text
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
