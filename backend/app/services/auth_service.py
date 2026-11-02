"""Authentication: credential verification with lockout, token issuance/rotation, logout, password change."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import AuditAction, AuditOutcome
from app.core.errors import AuthenticationError, InvalidCredentialsError, UnprocessableError
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    password_policy_errors,
    verify_password,
)
from app.db.types import utcnow
from app.models import User
from app.repositories import users as user_repo
from app.services import audit_service
from app.utils.text import normalize_email

logger = logging.getLogger("cybersentinel.auth")


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_max_age: int
    user: User


def _issue(settings: Settings, user: User) -> IssuedTokens:
    access, _ = create_token(settings, user_id=user.id, token_type="access", token_version=user.token_version, role=user.role)
    refresh, _ = create_token(settings, user_id=user.id, token_type="refresh", token_version=user.token_version)
    return IssuedTokens(
        access_token=access,
        access_expires_in=settings.access_token_ttl_minutes * 60,
        refresh_token=refresh,
        refresh_max_age=settings.refresh_token_ttl_hours * 3600,
        user=user,
    )


def authenticate(session: Session, settings: Settings, *, email: str, password: str, ip: str | None) -> IssuedTokens:
    """Verify credentials. Every failure returns the same generic error (no account enumeration)."""
    email = normalize_email(email)
    user = user_repo.get_by_email(session, email)
    now = utcnow()
    password_ok = verify_password(password, user.password_hash if user else None)

    if user is None:
        audit_service.record_independent(
            AuditAction.LOGIN_FAILURE,
            actor_id=None,
            outcome=AuditOutcome.FAILURE,
            ip_address=ip,
            details={"reason": "unknown_account"},
        )
        raise InvalidCredentialsError()
    if user.locked_until is not None and user.locked_until > now:
        audit_service.record_independent(
            AuditAction.LOGIN_LOCKED,
            actor_id=user.id,
            outcome=AuditOutcome.DENIED,
            ip_address=ip,
            resource_type="user",
            resource_id=user.id,
        )
        raise InvalidCredentialsError()
    if not user.is_active or not password_ok:
        if not password_ok:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.login_max_failed_attempts:
                user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
                user.failed_login_attempts = 0
            session.commit()
        audit_service.record_independent(
            AuditAction.LOGIN_FAILURE,
            actor_id=user.id,
            outcome=AuditOutcome.FAILURE,
            ip_address=ip,
            resource_type="user",
            resource_id=user.id,
            details={
                "reason": "inactive" if not user.is_active else "bad_password",
                "locked": user.locked_until is not None and user.locked_until > now,
            },
        )
        raise InvalidCredentialsError()

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    audit_service.record(
        session, AuditAction.LOGIN_SUCCESS, actor_id=user.id, ip_address=ip, resource_type="user", resource_id=user.id
    )
    session.commit()
    return _issue(settings, user)


def refresh(session: Session, settings: Settings, refresh_token: str | None) -> IssuedTokens:
    if not refresh_token:
        raise AuthenticationError("Your session has expired. Please sign in again.", code="session_expired")
    try:
        claims = decode_token(settings, refresh_token, expected_type="refresh")
    except TokenError:
        raise AuthenticationError("Your session has expired. Please sign in again.", code="session_expired") from None
    user = user_repo.get(session, claims.subject)
    if user is None or not user.is_active or user.token_version != claims.token_version:
        raise AuthenticationError("Your session has expired. Please sign in again.", code="session_expired")
    return _issue(settings, user)


def logout(session: Session, settings: Settings, *, user: User | None, refresh_token: str | None, ip: str | None) -> None:
    """Revoke every outstanding token of the user by bumping ``token_version``."""
    target = user
    if target is None and refresh_token:
        try:
            claims = decode_token(settings, refresh_token, expected_type="refresh")
            candidate = user_repo.get(session, claims.subject)
            if candidate and candidate.token_version == claims.token_version:
                target = candidate
        except TokenError:
            target = None
    if target is None:
        return
    target.token_version += 1
    audit_service.record(
        session, AuditAction.LOGOUT, actor_id=target.id, ip_address=ip, resource_type="user", resource_id=target.id
    )
    session.commit()


def validate_new_password(settings: Settings, password: str, email: str) -> None:
    errors = password_policy_errors(password, min_length=settings.password_min_length, email=email)
    if errors:
        raise UnprocessableError(
            "The new password does not meet the password policy.", code="weak_password", details={"password": errors}
        )


def change_password(session: Session, settings: Settings, *, user: User, current: str, new: str, ip: str | None) -> None:
    if not verify_password(current, user.password_hash):
        audit_service.record_independent(
            AuditAction.PASSWORD_CHANGE,
            actor_id=user.id,
            outcome=AuditOutcome.FAILURE,
            ip_address=ip,
            resource_type="user",
            resource_id=user.id,
            details={"reason": "bad_current_password"},
        )
        raise InvalidCredentialsError("The current password is incorrect.")
    if current == new:
        raise UnprocessableError("The new password must differ from the current password.", code="weak_password")
    validate_new_password(settings, new, user.email)
    user.password_hash = hash_password(new)
    user.token_version += 1
    audit_service.record(
        session, AuditAction.PASSWORD_CHANGE, actor_id=user.id, ip_address=ip, resource_type="user", resource_id=user.id
    )
    session.commit()
