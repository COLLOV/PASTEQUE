import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.database import Base
from insight_backend.core.security import hash_password
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
