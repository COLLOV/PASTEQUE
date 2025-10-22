from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..models.user import User


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
        show_dashboard_charts: bool = True,
    ) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
            is_active=is_active,
            show_dashboard_charts=show_dashboard_charts,
        )
        self.session.add(user)
        self.session.flush()
        log.info("User created: %s", username)
        return user

    def update_dashboard_visibility(self, user: User, *, show_dashboard_charts: bool) -> User:
        user.show_dashboard_charts = show_dashboard_charts
        self.session.add(user)
        self.session.flush()
        log.info(
            "Dashboard visibility updated for user=%s show_dashboard_charts=%s",
            user.username,
            show_dashboard_charts,
        )
        return user
