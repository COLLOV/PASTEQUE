from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ....core.config import settings
from ....core.database import get_session
from ....core.security import get_current_user
from ....models.user import User
from ....repositories.user_repository import UserRepository
from ....schemas.auth import CreateUserRequest, LoginRequest, TokenResponse, UserResponse
from ....services.auth_service import AuthService


router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    service = AuthService(UserRepository(session))
    user, token = service.authenticate(username=payload.username, password=payload.password)
    is_admin = user.username == settings.admin_username
    return TokenResponse(access_token=token, token_type="bearer", username=user.username, is_admin=is_admin)


@router.post("/auth/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserResponse:
    if current_user.username != settings.admin_username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    service = AuthService(UserRepository(session))
    user = service.create_user(username=payload.username, password=payload.password)
    session.commit()
    session.refresh(user)
    return UserResponse.from_model(user)
