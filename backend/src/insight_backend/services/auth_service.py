from __future__ import annotations

import logging

from fastapi import HTTPException, status

from ..core.security import hash_password, verify_password, create_access_token
from ..repositories.user_repository import UserRepository


log = logging.getLogger("insight.services.auth")


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def ensure_admin_user(self, username: str, password: str) -> bool:
        existing = self.repo.get_by_username(username)
        if existing:
            return False
        password_hash = hash_password(password)
        self.repo.create_user(username=username, password_hash=password_hash, is_active=True)
        log.info("Initial admin user ensured: %s", username)
        return True

    def authenticate(self, username: str, password: str) -> str:
        user = self.repo.get_by_username(username)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        return create_access_token(subject=user.username)
