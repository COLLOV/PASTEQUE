from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ....core.config import settings
from ....core.database import get_session
from ....core.security import get_current_user
from ....models.user import User
from ....repositories.user_repository import UserRepository
from ....repositories.user_table_permission_repository import UserTablePermissionRepository
from ....schemas.auth import (
    CreateUserRequest,
    LoginRequest,
    TokenResponse,
    UpdateUserPermissionsRequest,
    UserPermissionsOverviewResponse,
    UserResponse,
    ResetPasswordRequest,
    UserWithPermissionsResponse,
)
from ....services.auth_service import AuthService
from ....services.data_service import DataService


router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    service = AuthService(UserRepository(session))
    user, token = service.authenticate(username=payload.username, password=payload.password)
    is_admin = user.username == settings.admin_username
    return TokenResponse(access_token=token, token_type="bearer", username=user.username, is_admin=is_admin)


@router.get("/auth/users", response_model=UserPermissionsOverviewResponse)
async def list_users_with_permissions(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserPermissionsOverviewResponse:
    if current_user.username != settings.admin_username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    user_repo = UserRepository(session)
    users = user_repo.list_all()
    data_service = DataService()
    tables = [info.name for info in data_service.list_tables()]

    responses: list[UserWithPermissionsResponse] = []
    for user in users:
        if user.username == settings.admin_username:
            allowed = tables
        else:
            allowed = [perm.table_name for perm in user.table_permissions]
        responses.append(UserWithPermissionsResponse.from_model(user, allowed_tables=allowed))

    return UserPermissionsOverviewResponse(tables=tables, users=responses)


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


@router.put("/auth/users/{username}/table-permissions", response_model=UserWithPermissionsResponse)
async def update_user_table_permissions(
    username: str,
    payload: UpdateUserPermissionsRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserWithPermissionsResponse:
    if current_user.username != settings.admin_username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    user_repo = UserRepository(session)
    target = user_repo.get_by_username(username)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.username == settings.admin_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change admin permissions")

    data_service = DataService()
    available_tables = [info.name for info in data_service.list_tables()]
    available_lookup = {name.casefold() for name in available_tables}
    filtered = [name for name in payload.allowed_tables if name.casefold() in available_lookup]

    permissions_repo = UserTablePermissionRepository(session)
    updated = permissions_repo.set_allowed_tables(target.id, filtered)
    session.commit()
    session.refresh(target)
    return UserWithPermissionsResponse.from_model(target, allowed_tables=updated)


@router.post("/auth/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordRequest, session: Session = Depends(get_session)) -> None:
    service = AuthService(UserRepository(session))
    service.reset_password(
        username=payload.username,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    session.commit()
