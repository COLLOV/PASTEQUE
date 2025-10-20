from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ....core.database import get_session
from ....repositories.user_repository import UserRepository
from ....schemas.auth import LoginRequest, TokenResponse
from ....services.auth_service import AuthService


router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    service = AuthService(UserRepository(session))
    token = service.authenticate(username=payload.username, password=payload.password)
    return TokenResponse(access_token=token, token_type="bearer")
