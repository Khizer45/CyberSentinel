from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Email, RequestModel
from app.schemas.user import UserRead


class LoginRequest(RequestModel):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds")
    user: UserRead


class ChangePasswordRequest(RequestModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
