import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.database import Base
from insight_backend.core.security import hash_password
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


def test_admin_reset_sets_temp_and_forces_reset(session):
    repo = UserRepository(session)
    user = repo.create_user(
        username="dora",
        password_hash=hash_password("old"),
        is_active=True,
        must_reset_password=False,
    )
    session.commit()

    service = AuthService(repo)
    temp = service.admin_reset_password("dora")
    assert isinstance(temp, str) and len(temp) >= 12
    session.commit()

    # Now authenticating with the temp password should raise RESET_REQUIRED
    with pytest.raises(HTTPException) as exc:
        service.authenticate("dora", temp)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc.value.detail.get("code") == "PASSWORD_RESET_REQUIRED"

    # Simulate user resetting password with the temp password
    service.reset_password("dora", temp, "new-pass")
    session.commit()
    user, _ = service.authenticate("dora", "new-pass")
    assert user.username == "dora"


def test_admin_reset_missing_user(session):
    service = AuthService(UserRepository(session))
    with pytest.raises(HTTPException) as exc:
        service.admin_reset_password("unknown")
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND

