from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Iterable

from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from ..models.user import User


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class ResetPasswordRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)
    confirm_password: str = Field(..., min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_passwords(self) -> "ResetPasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserResponse(BaseModel):
    username: str
    is_active: bool
    created_at: datetime

    @classmethod
    def from_model(cls, user: "User") -> "UserResponse":
        return cls(username=user.username, is_active=user.is_active, created_at=user.created_at)


class UpdateUserPermissionsRequest(BaseModel):
    allowed_tables: list[str] = Field(default_factory=list)


class UserWithPermissionsResponse(BaseModel):
    username: str
    is_active: bool
    created_at: datetime
    allowed_tables: list[str]

    @classmethod
    def from_model(cls, user: "User", *, allowed_tables: Iterable[str]) -> "UserWithPermissionsResponse":
        return cls(
            username=user.username,
            is_active=user.is_active,
            created_at=user.created_at,
            allowed_tables=sorted(set(allowed_tables), key=str.casefold),
        )


class UserPermissionsOverviewResponse(BaseModel):
    tables: list[str]
    users: list[UserWithPermissionsResponse]
