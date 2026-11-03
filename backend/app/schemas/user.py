import uuid
from datetime import datetime

from pydantic import Field

from app.core.constants import UserRole
from app.schemas.common import ApiModel, Email, RequestModel


class UserRef(ApiModel):
    id: uuid.UUID
    display_name: str
    email: str


class UserRead(ApiModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(RequestModel):
    email: Email
    display_name: str = Field(min_length=1, max_length=120)
    role: UserRole
    password: str = Field(min_length=1, max_length=256)


class UserUpdate(RequestModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None


class PasswordResetRequest(RequestModel):
    new_password: str = Field(min_length=1, max_length=256)


class ProfileUpdate(RequestModel):
    display_name: str = Field(min_length=1, max_length=120)
