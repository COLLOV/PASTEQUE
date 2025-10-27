from __future__ import annotations

import logging

from sqlalchemy.orm import Session, selectinload

from ..models.user import User
from ..core.config import settings


log = logging.getLogger("insight.repositories.user")


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_username(self, username: str) -> User | None:
        return (
            self.session.query(User)
            .filter(User.username == username)
            .one_or_none()
        )

    def create_user(
        self,
        username: str,
        password_hash: str,
        *,
        is_active: bool = True,
        is_admin: bool = False,
        must_reset_password: bool = True,
    ) -> User:
        if is_admin and username != settings.admin_username:
            raise ValueError("Admin flag reserved for configured admin username")
        user = User(
            username=username,
            password_hash=password_hash,
            is_active=is_active,
            is_admin=is_admin,
            must_reset_password=must_reset_password,
        )
        self.session.add(user)
        self.session.flush()
        log.info(
            "User created: %s (admin=%s, must_reset_password=%s)",
            username,
            is_admin,
            must_reset_password,
        )
        return user

    def list_all(self) -> list[User]:
        users = (
            self.session.query(User)
            .options(selectinload(User.table_permissions))
            .order_by(User.username.asc())
            .all()
        )
        log.debug("Loaded %d users (admin scope)", len(users))
        return users
