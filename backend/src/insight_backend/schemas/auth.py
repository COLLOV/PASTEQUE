from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

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
    show_dashboard_charts: bool


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserResponse(BaseModel):
    username: str
    is_active: bool
    created_at: datetime
    show_dashboard_charts: bool

    @classmethod
    def from_model(cls, user: "User") -> "UserResponse":
        return cls(
            username=user.username,
            is_active=user.is_active,
            created_at=user.created_at,
            show_dashboard_charts=user.show_dashboard_charts,
        )


class UpdateUserPreferencesRequest(BaseModel):
    show_dashboard_charts: bool


class UserPreferencesResponse(BaseModel):
    show_dashboard_charts: bool

    @classmethod
    def from_model(cls, user: "User") -> "UserPreferencesResponse":
        return cls(show_dashboard_charts=user.show_dashboard_charts)
