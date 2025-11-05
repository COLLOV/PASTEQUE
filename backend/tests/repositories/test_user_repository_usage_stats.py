from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.config import settings
from insight_backend.core.database import Base
from insight_backend.models.chart import Chart  # noqa: F401 -- ensure table registration
from insight_backend.models.conversation import (  # noqa: F401 -- ensure table registration
    Conversation,
    ConversationEvent,  # noqa: F401
    ConversationMessage,
)
from insight_backend.models.user import User
from insight_backend.repositories.user_repository import UserRepository


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


def test_gather_usage_stats_returns_totals_and_per_user_entries(session):
    repo = UserRepository(session)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    recent = now - timedelta(days=1)
    older = now - timedelta(days=10)

    admin = User(
        username=settings.admin_username,
        password_hash="hash",
        is_active=True,
        is_admin=True,
    )
    alice = User(username="alice", password_hash="hash", is_active=True)
    bob = User(username="bob", password_hash="hash", is_active=True)
    session.add_all([admin, alice, bob])
    session.commit()
    session.refresh(alice)
    session.refresh(bob)

    alice_conversation = Conversation(
        user_id=alice.id,
        title="Alice recent conversation",
        created_at=recent,
        updated_at=recent,
    )
    bob_conversation = Conversation(
        user_id=bob.id,
        title="Bob older conversation",
        created_at=older,
        updated_at=older,
    )
    session.add_all([alice_conversation, bob_conversation])
    session.flush()

    session.add_all(
        [
            ConversationMessage(
                conversation_id=alice_conversation.id,
                role="user",
                content="Bonjour",
                created_at=recent,
            ),
            ConversationMessage(
                conversation_id=alice_conversation.id,
                role="assistant",
                content="Salut",
                created_at=now - timedelta(hours=2),
            ),
            ConversationMessage(
                conversation_id=bob_conversation.id,
                role="user",
                content="Ancien message",
                created_at=older,
            ),
        ]
    )

    session.add_all(
        [
            Chart(
                user_id=alice.id,
                prompt="chart",
                chart_url="http://localhost/chart.png",
                tool_name=None,
                chart_title=None,
                chart_description=None,
                chart_spec={},
                created_at=now - timedelta(hours=1),
            ),
            Chart(
                user_id=bob.id,
                prompt="old chart",
                chart_url="http://localhost/old.png",
                tool_name=None,
                chart_title=None,
                chart_description=None,
                chart_spec={},
                created_at=older,
            ),
        ]
    )

    session.commit()

    stats = repo.gather_usage_stats()

    totals = stats["totals"]
    assert totals["users"] == 3
    assert totals["conversations"] == 2
    assert totals["messages"] == 3
    assert totals["charts"] == 2
    assert totals["conversations_last_7_days"] == 1
    assert totals["messages_last_7_days"] == 2
    assert totals["charts_last_7_days"] == 1
    assert totals["active_users_last_7_days"] == 1

    per_user = {entry["username"]: entry for entry in stats["per_user"]}
    assert set(per_user.keys()) == {settings.admin_username, "alice", "bob"}

    alice_stats = per_user["alice"]
    assert alice_stats["conversations"] == 1
    assert alice_stats["messages"] == 2
    assert alice_stats["charts"] == 1
    assert alice_stats["last_activity_at"] is not None
    assert alice_stats["last_activity_at"] >= now - timedelta(hours=2)
    assert alice_stats["created_at"].tzinfo is not None

    bob_stats = per_user["bob"]
    assert bob_stats["conversations"] == 1
    assert bob_stats["messages"] == 1
    assert bob_stats["charts"] == 1
    assert bob_stats["last_activity_at"] is not None
    assert bob_stats["last_activity_at"] <= older

    admin_stats = per_user[settings.admin_username]
    assert admin_stats["conversations"] == 0
    assert admin_stats["messages"] == 0
    assert admin_stats["charts"] == 0
    assert admin_stats["last_activity_at"] is None
