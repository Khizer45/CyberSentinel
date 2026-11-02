"""Administrator user management (FR-17)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AdminUser, ClientIP, DbSession, Pagination, SettingsDep
from app.core.constants import UserRole
from app.models import User
from app.repositories import users as user_repo
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.user import PasswordResetRequest, UserCreate, UserRead, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/admin/users", tags=["users"], responses=ERROR_RESPONSES)
UserSort = Literal["created_at", "-created_at", "email", "-email", "display_name", "-display_name", "role", "-role"]


@router.get("", response_model=Page[UserRead])
def list_users(
    admin: AdminUser,
    db: DbSession,
    page: Pagination,
    role: UserRole | None = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: UserSort = "-created_at",
) -> Page[UserRead]:
    items, total = user_repo.list_users(db, role=role, is_active=is_active, q=q, sort=sort, limit=page.limit, offset=page.offset)
    return Page[UserRead](items=[UserRead.model_validate(u) for u in items], total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, admin: AdminUser, db: DbSession, settings: SettingsDep, ip: ClientIP) -> User:
    return user_service.create_user(db, settings, actor=admin, payload=payload, ip=ip)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> User:
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: uuid.UUID, payload: UserUpdate, admin: AdminUser, db: DbSession, ip: ClientIP) -> User:
    return user_service.update_user(db, actor=admin, user_id=user_id, payload=payload, ip=ip)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID, payload: PasswordResetRequest, admin: AdminUser, db: DbSession, settings: SettingsDep, ip: ClientIP
) -> Response:
    user_service.reset_password(db, settings, actor=admin, user_id=user_id, new_password=payload.new_password, ip=ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
