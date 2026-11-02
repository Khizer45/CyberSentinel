"""Authentication endpoints (FR-01, SEC-10)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import (
    ClientIP,
    CurrentUser,
    DbSession,
    SettingsDep,
    enforce_rate_limit,
    get_optional_user,
    rate_limit,
)
from app.core.config import Settings
from app.core.errors import PermissionDeniedError
from app.models import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.schemas.common import ERROR_RESPONSES
from app.schemas.user import ProfileUpdate, UserRead
from app.services import auth_service, user_service
from app.services.auth_service import IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)
COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, settings: Settings, tokens: IssuedTokens) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=tokens.refresh_token,
        max_age=tokens.refresh_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=COOKIE_PATH,
    )


def _token_response(tokens: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token, expires_in=tokens.access_expires_in, user=UserRead.model_validate(tokens.user)
    )


def _check_origin(request: Request, settings: Settings) -> None:
    """CSRF defence for cookie-authenticated endpoints: browsers always send Origin on POST."""
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in settings.cors_origins:
        raise PermissionDeniedError("Cross-origin request rejected.", code="origin_not_allowed")


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit("login", "rate_limit_login"))])
def login(
    payload: LoginRequest, request: Request, response: Response, db: DbSession, settings: SettingsDep, ip: ClientIP
) -> TokenResponse:
    """Exchange e-mail and password for a short-lived access token; sets an HttpOnly refresh cookie."""
    enforce_rate_limit(request, settings, "login-account", settings.rate_limit_login, payload.email)
    tokens = auth_service.authenticate(db, settings, email=payload.email, password=payload.password, ip=ip)
    _set_refresh_cookie(response, settings, tokens)
    return _token_response(tokens)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(rate_limit("refresh", "rate_limit_default"))])
def refresh(request: Request, response: Response, db: DbSession, settings: SettingsDep) -> TokenResponse:
    """Issue a new access token from the refresh cookie (the cookie is rotated)."""
    _check_origin(request, settings)
    tokens = auth_service.refresh(db, settings, request.cookies.get(settings.refresh_cookie_name))
    _set_refresh_cookie(response, settings, tokens)
    return _token_response(tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    ip: ClientIP,
    user: Annotated[User | None, Depends(get_optional_user)],
) -> Response:
    """Revoke all of the user's tokens and clear the refresh cookie."""
    _check_origin(request, settings)
    auth_service.logout(db, settings, user=user, refresh_token=request.cookies.get(settings.refresh_cookie_name), ip=ip)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_samesite,
    )
    return response


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserRead)
def update_me(payload: ProfileUpdate, user: CurrentUser, db: DbSession, ip: ClientIP) -> User:
    return user_service.update_profile(db, user=user, display_name=payload.display_name, ip=ip)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("change-password", "rate_limit_login", "user"))],
)
def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, db: DbSession, settings: SettingsDep, ip: ClientIP
) -> Response:
    """Change the caller's password; all existing sessions are revoked."""
    auth_service.change_password(db, settings, user=user, current=payload.current_password, new=payload.new_password, ip=ip)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
