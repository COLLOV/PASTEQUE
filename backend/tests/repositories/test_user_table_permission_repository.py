import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.database import Base
from insight_backend.models.user import User
from insight_backend.models.user_table_permission import UserTablePermission  # noqa: F401 - ensure table registration
from insight_backend.repositories.user_table_permission_repository import UserTablePermissionRepository


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


def test_set_and_get_allowed_tables(session):
    user = User(username="alice", password_hash="hash", is_active=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    repo = UserTablePermissionRepository(session)

    updated = repo.set_allowed_tables(user.id, ["sales", "Sales", "  finance  "])
    session.commit()
    assert updated == ["finance", "sales"]
    assert repo.get_allowed_tables(user.id) == ["finance", "sales"]

    updated = repo.set_allowed_tables(user.id, ["Sales"])
    session.commit()
    assert updated == ["Sales"]
    assert repo.get_allowed_tables(user.id) == ["sales"]


def test_set_allowed_tables_removes_missing_entries(session):
    user = User(username="bob", password_hash="hash", is_active=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    repo = UserTablePermissionRepository(session)
    repo.set_allowed_tables(user.id, ["tickets", "support"])
    session.commit()

    repo.set_allowed_tables(user.id, ["support"])
    session.commit()

    remaining = repo.get_allowed_tables(user.id)
    assert remaining == ["support"]
