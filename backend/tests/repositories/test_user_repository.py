import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.database import Base
from insight_backend.core.config import settings
from insight_backend.models.user import User
from insight_backend.repositories.user_repository import UserRepository


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    sess = Session()
    try:
        yield sess
    finally:
        sess.close()


def _make_admin(session) -> User:
    admin = User(
        username=settings.admin_username,
        password_hash="hashed",
        is_admin=True,
        must_reset_password=False,
    )
    session.add(admin)
    session.flush()
    return admin


def test_admin_rag_debug_toggle(session):
    admin = _make_admin(session)
    repo = UserRepository(session)

    assert repo.get_admin_rag_debug() is False

    enabled = repo.set_admin_rag_debug(True)
    assert enabled is True
    session.refresh(admin)
    assert admin.settings.get("debug_show_rag_rows") is True
    assert repo.get_admin_rag_debug() is True

    disabled = repo.set_admin_rag_debug(False)
    assert disabled is False
    session.refresh(admin)
    assert admin.settings.get("debug_show_rag_rows") is False
    assert repo.get_admin_rag_debug() is False
