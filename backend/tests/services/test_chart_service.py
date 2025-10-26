import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from insight_backend.core.config import settings
from insight_backend.core.database import Base
from insight_backend.models.chart import Chart  # noqa: F401 - ensure table registration
from insight_backend.models.user import User
from insight_backend.repositories.chart_repository import ChartRepository
from insight_backend.services.chart_service import ChartService


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


@pytest.fixture
def users(session):
    alice = User(username="alice", password_hash="hash", is_active=True)
    bob = User(username="bob", password_hash="hash", is_active=True)
    admin = User(
        username=settings.admin_username,
        password_hash="hash",
        is_active=True,
        is_admin=True,
    )
    session.add_all([alice, bob, admin])
    session.commit()
    session.refresh(alice)
    session.refresh(bob)
    session.refresh(admin)
    return alice, bob, admin


def test_save_chart_persists_and_scopes_to_owner(session, users):
    alice, bob, _ = users
    service = ChartService(ChartRepository(session))

    chart = service.save_chart(
        user=alice,
        prompt="Bar chart for sales",
        chart_url="http://example.com/chart.png",
        tool_name="generate_bar_chart",
        chart_title="Sales by Region",
        chart_description="Comparaison des ventes par région.",
        chart_spec={"type": "bar"},
    )
    session.commit()
    session.refresh(chart)

    assert chart.user_id == alice.id
    assert chart.prompt == "Bar chart for sales"

    charts_for_alice = service.list_charts(alice)
    assert len(charts_for_alice) == 1
    assert charts_for_alice[0].user_id == alice.id

    charts_for_bob = service.list_charts(bob)
    assert charts_for_bob == []


def test_admin_can_see_all_charts(session, users):
    alice, _, admin = users
    service = ChartService(ChartRepository(session))

    chart = service.save_chart(
        user=alice,
        prompt="Line chart",
        chart_url="http://example.com/line.png",
        tool_name=None,
        chart_title=None,
        chart_description=None,
        chart_spec=None,
    )
    session.commit()
    session.refresh(chart)

    charts_for_admin = service.list_charts(admin)
    assert len(charts_for_admin) == 1
    assert charts_for_admin[0].user_id == alice.id
