import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.database import Base
from insight_backend.models.user import User
from insight_backend.models.conversation import Conversation
from insight_backend.repositories.conversation_repository import ConversationRepository


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


def _mk_user_and_conversation(session):
    user = User(username="u", password_hash="x")
    session.add(user)
    session.flush()
    conv = Conversation(user_id=user.id, title="t")
    session.add(conv)
    session.flush()
    return user, conv


def test_excluded_tables_case_insensitive_deduplication(session):
    user, conv = _mk_user_and_conversation(session)
    repo = ConversationRepository(session)
    saved = repo.set_excluded_tables(conversation_id=conv.id, tables=["Tickets", "tickets", "TICKETS", "  tickets  "])
    assert saved == ["Tickets"], "expected first-casing preserved and deduplicated"
    out = repo.get_excluded_tables(conversation_id=conv.id)
    assert len(out) == 1
    assert out[0].lower() == "tickets"


def test_excluded_tables_empty_list(session):
    user, conv = _mk_user_and_conversation(session)
    repo = ConversationRepository(session)
    saved = repo.set_excluded_tables(conversation_id=conv.id, tables=[])
    assert saved == []
    out = repo.get_excluded_tables(conversation_id=conv.id)
    assert out == []

