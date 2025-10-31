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

    # ----- Settings helpers -----
    def get_settings(self, *, user_id: int) -> dict:
        user = self.session.query(User).filter(User.id == user_id).one_or_none()
        return dict(user.settings or {}) if user else {}

    def set_settings(self, *, user_id: int, settings: dict) -> dict:
        payload = dict(settings or {})
        self.session.query(User).filter(User.id == user_id).update({User.settings: payload})
        log.info("User settings updated (user_id=%s, keys=%s)", user_id, ",".join(sorted(payload.keys())))
        return payload

    def get_default_excluded_tables(self, *, user_id: int) -> list[str]:
        s = self.get_settings(user_id=user_id)
        raw = s.get("default_exclude_tables") if isinstance(s, dict) else None
        if not isinstance(raw, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for item in raw:
            if isinstance(item, str) and item.strip():
                key = item.strip()
                if key.casefold() in seen:
                    continue
                seen.add(key.casefold())
                out.append(key)
        return out

    def set_default_excluded_tables(self, *, user_id: int, tables: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in tables:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        s = self.get_settings(user_id=user_id)
        s["default_exclude_tables"] = normalized
        self.set_settings(user_id=user_id, settings=s)
        return normalized
