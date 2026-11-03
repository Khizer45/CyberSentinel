"""Audit log review (FR-18) — administrators only."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession, Pagination, as_utc
from app.core.constants import AuditOutcome
from app.models import User
from app.repositories import audit_logs as audit_repo
from app.schemas.audit import AuditLogRead
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.user import UserRef

router = APIRouter(prefix="/audit-logs", tags=["audit"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[AuditLogRead])
def list_audit_logs(
    admin: AdminUser,
    db: DbSession,
    page: Pagination,
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor_user_id: uuid.UUID | None = None,
    resource_type: Annotated[str | None, Query(max_length=60)] = None,
    resource_id: uuid.UUID | None = None,
    outcome: AuditOutcome | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Page[AuditLogRead]:
    items, total = audit_repo.list_audit_logs(
        db,
        action=action,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        date_from=as_utc(date_from),
        date_to=as_utc(date_to),
        limit=page.limit,
        offset=page.offset,
    )
    actors: dict[uuid.UUID, UserRef | None] = {}
    for entry in items:
        if entry.actor_user_id and entry.actor_user_id not in actors:
            actor = db.get(User, entry.actor_user_id)
            actors[entry.actor_user_id] = UserRef.model_validate(actor) if actor else None
    rows = [
        AuditLogRead(
            id=e.id,
            actor=actors.get(e.actor_user_id) if e.actor_user_id else None,
            action=e.action,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            request_id=e.request_id,
            ip_address=str(e.ip_address) if e.ip_address else None,
            outcome=AuditOutcome(e.outcome),
            details=e.details,
            created_at=e.created_at,
        )
        for e in items
    ]
    return Page[AuditLogRead](items=rows, total=total, limit=page.limit, offset=page.offset)
