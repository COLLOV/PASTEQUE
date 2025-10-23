import pytest

from insight_backend.core.config import settings
from insight_backend.core.security import user_is_admin
from insight_backend.models.user import User


def make_user(username: str, is_admin: bool) -> User:
    return User(username=username, password_hash="hash", is_active=True, is_admin=is_admin)


def test_user_is_admin_true_when_both_flag_and_username_match():
    user = make_user(settings.admin_username, True)
    assert user_is_admin(user) is True


def test_user_is_admin_requires_flag():
    user = make_user(settings.admin_username, False)
    assert user_is_admin(user) is False


def test_user_is_admin_requires_username():
    user = make_user("someone", True)
    assert user_is_admin(user) is False

