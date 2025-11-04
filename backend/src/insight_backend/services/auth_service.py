from __future__ import annotations

import logging

from fastapi import HTTPException, status

from ..core.security import hash_password, verify_password, create_access_token
from ..models.user import User
from ..repositories.user_repository import UserRepository


log = logging.getLogger("insight.services.auth")


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def ensure_admin_user(self, username: str, password: str) -> bool:
        existing = self.repo.get_by_username(username)
        if existing:
            if not existing.is_admin:
                existing.is_admin = True
                self.repo.session.flush()
                log.info("Existing admin user flagged with admin privileges: %s", username)
            return False
        password_hash = hash_password(password)
        self.repo.create_user(
            username=username,
            password_hash=password_hash,
            is_active=True,
            is_admin=True,
            must_reset_password=True,
        )
        log.info("Initial admin user ensured: %s", username)
        return True

    def authenticate(self, username: str, password: str) -> tuple[User, str]:
        user = self.repo.get_by_username(username)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if user.must_reset_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PASSWORD_RESET_REQUIRED", "message": "Password reset required"},
            )
        token = create_access_token(subject=user.username)
        return user, token

    def create_user(self, username: str, password: str) -> User:
        existing = self.repo.get_by_username(username)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
        password_hash = hash_password(password)
        user = self.repo.create_user(
            username=username,
            password_hash=password_hash,
            is_active=True,
            must_reset_password=True,
        )
        log.info("User created via admin API: %s", username)
        return user

    def reset_password(self, username: str, current_password: str, new_password: str) -> None:
        user = self.repo.get_by_username(username)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        user.password_hash = hash_password(new_password)
        user.must_reset_password = False
        log.info("Password reset for user: %s", username)

    def delete_user(self, username: str) -> None:
        user = self.repo.get_by_username(username)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        # Never allow deleting the configured admin account
        from ..core.security import user_is_admin  # local import to avoid cycles
        if user_is_admin(user):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete admin user")
        self.repo.delete_user(user)
        log.info("User removed via admin API: %s", username)

    def admin_reset_password(self, username: str) -> str:
        """Generate a temporary password and force reset on next login.

        Returns the plaintext temporary password (do not log it).
        """
        import secrets
        import string

        user = self.repo.get_by_username(username)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        alphabet = string.ascii_letters + string.digits
        temp_password = "".join(secrets.choice(alphabet) for _ in range(16))
        user.password_hash = hash_password(temp_password)
        user.must_reset_password = True
        # Do not log the password; only the username for audit trail
        log.info("Temporary password set; user must reset at next login: %s", username)
        return temp_password
