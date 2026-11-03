"""Password hashing and token handling (SEC-01, SEC-10).

* Passwords: Argon2id (``argon2-cffi`` defaults), automatic re-hash when parameters change.
* Access tokens: short-lived JWT (default 15 min) sent as ``Authorization: Bearer``; kept in memory by the SPA.
* Refresh tokens: JWT in an ``HttpOnly``, ``SameSite=Strict``, path-scoped cookie (default 12 h).
* Revocation: both token types carry the user's ``token_version`` (``tv``); bumping it on logout, password
  change, role change or deactivation invalidates every outstanding token of that user.
"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

_hasher = PasswordHasher()
# Hash of a random value, used to equalize timing when the e-mail does not exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time-ish verification; always performs one Argon2 verification."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def password_policy_errors(password: str, *, min_length: int, email: str | None = None) -> list[str]:
    """Length-first policy (NIST SP 800-63B style) plus minimal composition and context checks."""
    errors = []
    if len(password) < min_length:
        errors.append(f"must be at least {min_length} characters long")
    if len(password) > 128:
        errors.append("must be at most 128 characters long")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        errors.append("must contain at least one letter and one digit")
    if password.strip() != password:
        errors.append("must not start or end with whitespace")
    if email and email.split("@", 1)[0].lower() in password.lower() and len(email.split("@", 1)[0]) >= 4:
        errors.append("must not contain the e-mail user name")
    return errors


@dataclass(frozen=True)
class TokenClaims:
    subject: uuid.UUID
    token_type: TokenType
    token_version: int
    role: str | None
    expires_at: datetime
    jti: str


class TokenError(Exception):
    """Raised for any invalid, expired or malformed token (details are not exposed to clients)."""


def create_token(
    settings: Settings, *, user_id: uuid.UUID, token_type: TokenType, token_version: int, role: str | None = None
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"
        else timedelta(hours=settings.refresh_token_ttl_hours)
    )
    expires = now + ttl
    payload = {
        "sub": str(user_id),
        "typ": token_type,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid.uuid4().hex,
    }
    if role is not None:
        payload["role"] = role
    token = jwt.encode(payload, settings.auth_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, expires


def decode_token(settings: Settings, token: str, *, expected_type: TokenType) -> TokenClaims:
    if not token or len(token) > 4096:
        raise TokenError("missing or oversized token")
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # never accept "none" or other algorithms
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "typ", "tv", "jti"]},
            leeway=5,
        )
    except jwt.PyJWTError as exc:
        raise TokenError(type(exc).__name__) from exc
    if payload.get("typ") != expected_type:
        raise TokenError("wrong token type")
    try:
        subject = uuid.UUID(str(payload["sub"]))
        version = int(payload["tv"])
    except (ValueError, TypeError) as exc:
        raise TokenError("malformed claims") from exc
    return TokenClaims(
        subject=subject,
        token_type=expected_type,
        token_version=version,
        role=payload.get("role"),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
        jti=str(payload["jti"]),
    )
