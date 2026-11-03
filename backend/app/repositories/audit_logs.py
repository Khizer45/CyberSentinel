from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.repositories.base import paginate_scalars


def list_audit_logs(
    session: Session,
    *,
    action: str | None,
    actor_user_id: uuid.UUID | None,
    resource_type: str | None,
    resource_id: uuid.UUID | None,
    outcome: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[AuditLog], int]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_user_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == resource_id)
    if outcome:
        stmt = stmt.where(AuditLog.outcome == outcome)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    return paginate_scalars(session, stmt, limit=limit, offset=offset)
