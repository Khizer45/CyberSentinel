"""Administrator user management (FR-17) with privilege-escalation safeguards."""

from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import AuditAction, UserRole
from app.core.errors import ConflictError, NotFoundError
from app.core.security import hash_password
from app.models import User
from app.repositories import users as user_repo
from app.schemas.user import UserCreate, UserUpdate
from app.services import audit_service
from app.services.auth_service import validate_new_password
from app.utils.text import clean_text, normalize_email


def get_user(session: Session, user_id: uuid.UUID) -> User:
    user = user_repo.get(session, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    return user


def create_user(session: Session, settings: Settings, *, actor: User, payload: UserCreate, ip: str | None) -> User:
    email = normalize_email(payload.email)
    validate_new_password(settings, payload.password, email)
    if user_repo.get_by_email(session, email):
        raise ConflictError("A user with this e-mail address already exists.", code="email_taken")
    user = User(
        email=email,
        display_name=clean_text(payload.display_name, max_length=120),
        role=payload.role.value,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ConflictError("A user with this e-mail address already exists.", code="email_taken") from None
    audit_service.record(
        session,
        AuditAction.USER_CREATE,
        actor_id=actor.id,
        ip_address=ip,
        resource_type="user",
        resource_id=user.id,
        details={"role": user.role},
    )
    session.commit()
    return user


def _ensure_not_last_admin(session: Session, user: User) -> None:
    if user.role == UserRole.ADMIN and user.is_active and user_repo.count_active_admins(session) <= 1:
        raise ConflictError("At least one active administrator must remain.", code="last_admin")


def update_user(session: Session, *, actor: User, user_id: uuid.UUID, payload: UserUpdate, ip: str | None) -> User:
    user = get_user(session, user_id)
    changes: dict[str, object] = {}
    if payload.display_name is not None and payload.display_name != user.display_name:
        user.display_name = clean_text(payload.display_name, max_length=120)
        changes["display_name"] = True
    if payload.role is not None and payload.role.value != user.role:
        if user.role == UserRole.ADMIN:
            _ensure_not_last_admin(session, user)
        changes["role"] = {"from": user.role, "to": payload.role.value}
        user.role = payload.role.value
        user.token_version += 1  # force re-authentication with the new role
    if payload.is_active is not None and payload.is_active != user.is_active:
        if not payload.is_active:
            _ensure_not_last_admin(session, user)
            user.token_version += 1
        else:
            user.failed_login_attempts = 0
            user.locked_until = None
        user.is_active = payload.is_active
        changes["is_active"] = payload.is_active
    if not changes:
        return user
    if "role" in changes:
        audit_service.record(
            session,
            AuditAction.USER_ROLE_CHANGE,
            actor_id=actor.id,
            ip_address=ip,
            resource_type="user",
            resource_id=user.id,
            details=changes["role"],
        )  # type: ignore[arg-type]
    if "is_active" in changes:
        action = AuditAction.USER_ACTIVATE if user.is_active else AuditAction.USER_DEACTIVATE
        audit_service.record(session, action, actor_id=actor.id, ip_address=ip, resource_type="user", resource_id=user.id)
    if "display_name" in changes:
        audit_service.record(
            session,
            AuditAction.USER_UPDATE,
            actor_id=actor.id,
            ip_address=ip,
            resource_type="user",
            resource_id=user.id,
            details={"fields": ["display_name"]},
        )
    session.commit()
    return user


def reset_password(
    session: Session, settings: Settings, *, actor: User, user_id: uuid.UUID, new_password: str, ip: str | None
) -> User:
    user = get_user(session, user_id)
    validate_new_password(settings, new_password, user.email)
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    audit_service.record(
        session, AuditAction.USER_PASSWORD_RESET, actor_id=actor.id, ip_address=ip, resource_type="user", resource_id=user.id
    )
    session.commit()
    return user


def update_profile(session: Session, *, user: User, display_name: str, ip: str | None) -> User:
    user.display_name = clean_text(display_name, max_length=120)
    audit_service.record(
        session,
        AuditAction.USER_UPDATE,
        actor_id=user.id,
        ip_address=ip,
        resource_type="user",
        resource_id=user.id,
        details={"fields": ["display_name"], "self_service": True},
    )
    session.commit()
    return user
