import pytest

from insight_backend.services.router_service import RouterService
from insight_backend.core.config import settings


@pytest.fixture
def router():
    return RouterService()


def test_block_short_greeting(router):
    d = router.decide("Bonjour")
    assert d.allow is False
    assert d.route == "none"


def test_allow_question_keywords(router):
    d = router.decide("Combien de tickets en juin ?")
    assert d.allow is True
    assert d.route == "data"


def test_allow_time_hint(router):
    d = router.decide("Et en juin ?")
    assert d.allow is True
    assert d.route == "data"


def test_allow_numbers(router):
    d = router.decide("Montre les stats 2024")
    assert d.allow is True
    assert d.route == "data"


def test_feedback_route(router):
    d = router.decide("retours NPS et avis clients")
    assert d.allow is True
    assert d.route == "feedback"


def test_foyer_route(router):
    d = router.decide("Analyse foyer par ménage")
    assert d.allow is True
    assert d.route == "foyer"


def test_empty_message(router):
    d = router.decide("")
    assert d.allow is False
    assert d.route == "none"
@pytest.fixture(autouse=True)
def force_rule_mode():
    prev = settings.router_mode
    settings.router_mode = "rule"
    try:
        yield
    finally:
        settings.router_mode = prev
