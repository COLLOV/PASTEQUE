import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.database import Base
from insight_backend.models.user import User
from insight_backend.models.conversation import Conversation, ConversationMessage
from insight_backend.repositories.feedback_repository import FeedbackRepository


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


def _mk(session):
    user = User(username="u", password_hash="x")
    session.add(user)
    session.flush()
    conv = Conversation(user_id=user.id, title="t")
    session.add(conv)
    session.flush()
    msg = ConversationMessage(conversation_id=conv.id, role="assistant", content="hello")
    session.add(msg)
    session.flush()
    return user, conv, msg


def test_upsert_create_and_update(session):
    user, conv, msg = _mk(session)
    repo = FeedbackRepository(session)

    fb = repo.upsert(user_id=user.id, conversation_id=conv.id, message_id=msg.id, value="up")
    session.commit()
    assert fb.id is not None
    assert fb.value == "up"

    updated = repo.upsert(user_id=user.id, conversation_id=conv.id, message_id=msg.id, value="down")
    session.commit()
    assert updated.id == fb.id
    assert updated.value == "down"

    all_fb = repo.list_for_conversation_user(conversation_id=conv.id, user_id=user.id)
    assert len(all_fb) == 1
    assert all_fb[0].value == "down"


def test_upsert_rejects_invalid_value(session):
    user, conv, msg = _mk(session)
    repo = FeedbackRepository(session)
    with pytest.raises(ValueError):
        repo.upsert(user_id=user.id, conversation_id=conv.id, message_id=msg.id, value="maybe")


def test_delete_feedback(session):
    user, conv, msg = _mk(session)
    repo = FeedbackRepository(session)
    fb = repo.upsert(user_id=user.id, conversation_id=conv.id, message_id=msg.id, value="up")
    session.commit()

    repo.delete(fb)
    session.commit()

    assert repo.get_by_id(fb.id) is None
