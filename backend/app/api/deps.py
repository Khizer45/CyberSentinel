"""FastAPI dependencies: settings/components, authentication, RBAC, pagination and rate limits."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, parse_rate
from app.core.constants import AuditAction, AuditOutcome, UserRole
from app.core.context import user_id_var
from app.core.errors import AuthenticationError, PermissionDeniedError, RateLimitedError
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import TokenError, decode_token
from app.db.session import get_db
from app.models import User
from app.services import audit_service
from app.services.experiment_service import ExperimentStore
from app.services.job_runner import JobRunner
from app.services.model_registry_service import ModelRegistry
from app.services.risk_scoring_service import RiskScoringService
from app.services.storage_service import UploadStorage
from app.utils.ip import normalize_ip

bearer_scheme = HTTPBearer(auto_error=False, description="Short-lived access token from POST /api/v1/auth/login")

DbSession = Annotated[Session, Depends(get_db)]


def settings_dep(request: Request) -> Settings:
    """Settings of the running application (injected by the app factory; tests supply their own)."""
    return request.app.state.settings  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(settings_dep)]


def registry_dep(request: Request) -> ModelRegistry:
    return request.app.state.registry  # type: ignore[no-any-return]


def runner_dep(request: Request) -> JobRunner:
    return request.app.state.runner  # type: ignore[no-any-return]


def risk_dep(request: Request) -> RiskScoringService:
    return request.app.state.risk  # type: ignore[no-any-return]


def storage_dep(request: Request) -> UploadStorage:
    return request.app.state.storage  # type: ignore[no-any-return]


def experiments_dep(request: Request) -> ExperimentStore:
    return request.app.state.experiments  # type: ignore[no-any-return]


Registry = Annotated[ModelRegistry, Depends(registry_dep)]
Runner = Annotated[JobRunner, Depends(runner_dep)]
Risk = Annotated[RiskScoringService, Depends(risk_dep)]
Storage = Annotated[UploadStorage, Depends(storage_dep)]
Experiments = Annotated[ExperimentStore, Depends(experiments_dep)]


def client_ip(request: Request, settings: Settings) -> str | None:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return normalize_ip(forwarded.split(",")[0])
    return normalize_ip(request.client.host) if request.client else None


def ip_dep(request: Request, settings: SettingsDep) -> str | None:
    return client_ip(request, settings)


ClientIP = Annotated[str | None, Depends(ip_dep)]


def _user_from_token(db: Session, settings: Settings, token: str) -> User:
    try:
        claims = decode_token(settings, token, expected_type="access")
    except TokenError:
        raise AuthenticationError(
            "The access token is invalid or has expired.", code="invalid_token", headers={"WWW-Authenticate": "Bearer"}
        ) from None
    user = db.get(User, claims.subject)
    if user is None or not user.is_active or user.token_version != claims.token_version:
        raise AuthenticationError(
            "The access token is no longer valid.", code="invalid_token", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


def get_current_user(
    db: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError(headers={"WWW-Authenticate": "Bearer"})
    user = _user_from_token(db, settings, credentials.credentials)
    user_id_var.set(str(user.id))
    return user


def get_optional_user(
    db: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User | None:
    if credentials is None:
        return None
    try:
        return _user_from_token(db, settings, credentials.credentials)
    except AuthenticationError:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., User]:
    allowed = {role.value for role in roles}

    def dependency(request: Request, user: CurrentUser, settings: SettingsDep) -> User:
        if user.role not in allowed:
            audit_service.record_independent(
                AuditAction.ACCESS_DENIED,
                actor_id=user.id,
                outcome=AuditOutcome.DENIED,
                ip_address=client_ip(request, settings),
                details={"method": request.method, "path": request.url.path, "role": user.role},
            )
            raise PermissionDeniedError()
        return user

    return dependency


AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
AnalystUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.ANALYST))]
AnyUser = CurrentUser


@dataclass(frozen=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: Annotated[int, Query(ge=1, le=100, description="Page size (max 100)")] = 25,
    offset: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


Pagination = Annotated[PageParams, Depends(page_params)]


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def limiter(request: Request) -> SlidingWindowLimiter:
    return request.app.state.rate_limiter  # type: ignore[no-any-return]


def enforce_rate_limit(request: Request, settings: Settings, name: str, rate: str, identity: str) -> None:
    if not settings.rate_limit_enabled:
        return
    limit, window = parse_rate(rate)
    retry_after = limiter(request).hit(f"{name}:{identity}", limit, window)
    if retry_after is not None:
        raise RateLimitedError(retry_after)


def rate_limit(name: str, setting: str, key: Literal["ip", "user"] = "ip") -> Callable[..., None]:
    """Dependency factory: ``key='user'`` limits per authenticated user, ``'ip'`` per client address."""

    if key == "user":

        def by_user(request: Request, settings: SettingsDep, user: CurrentUser) -> None:
            enforce_rate_limit(request, settings, name, getattr(settings, setting), str(user.id))

        return by_user

    def by_ip(request: Request, settings: SettingsDep) -> None:
        enforce_rate_limit(request, settings, name, getattr(settings, setting), client_ip(request, settings) or "unknown")

    return by_ip
