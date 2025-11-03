import pytest
from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.config import settings
from insight_backend.core.database import Base
from insight_backend.core.security import hash_password
from insight_backend.models.user import User
from insight_backend.models.chart import Chart
from insight_backend.models.conversation import Conversation
from insight_backend.repositories.user_repository import UserRepository
from insight_backend.repositories.user_table_permission_repository import (
    UserTablePermissionRepository,
)
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


def _make_user_with_data(session, username: str) -> User:
    repo = UserRepository(session)
    user = repo.create_user(
        username=username,
        password_hash=hash_password("pwd"),
        is_active=True,
        must_reset_password=False,
    )
    # Attach permissions
    perm_repo = UserTablePermissionRepository(session)
    perm_repo.set_allowed_tables(user.id, ["files.tickets", "files.users"])
    # Attach a conversation
    conv = Conversation(user_id=user.id, title="Hello")
    session.add(conv)
    # Attach a chart
    chart = Chart(
        user_id=user.id,
        prompt="demo",
        chart_url="http://example/chart",
        tool_name="vega",
    )
    session.add(chart)
    session.commit()
    session.refresh(user)
    return user


def test_delete_user_cascades_related_data(session):
    user = _make_user_with_data(session, "charlie")
    # Pre-assert
    assert session.query(Conversation).count() == 1
    assert session.query(Chart).count() == 1
    assert len(user.table_permissions) == 2

    service = AuthService(UserRepository(session))
    service.delete_user(username="charlie")
    session.commit()

    # User removed
    assert UserRepository(session).get_by_username("charlie") is None
    # Cascades removed
    assert session.query(Conversation).count() == 0
    assert session.query(Chart).count() == 0


def test_delete_admin_user_is_forbidden(session):
    # Create configured admin user
    admin = User(
        username=settings.admin_username,
        password_hash=hash_password("admin"),
        is_active=True,
        is_admin=True,
        must_reset_password=False,
    )
    session.add(admin)
    session.commit()

    service = AuthService(UserRepository(session))
    with pytest.raises(HTTPException) as exc:
        service.delete_user(username=settings.admin_username)
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_delete_user_404_when_missing(session):
    service = AuthService(UserRepository(session))
    with pytest.raises(HTTPException) as exc:
        service.delete_user(username="ghost")
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND

