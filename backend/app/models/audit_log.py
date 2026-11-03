"""``audit_logs`` table (ERD 4.7): append-only security/accountability events.

``details`` only contains allowlisted metadata assembled by :mod:`app.services.audit_service`;
credentials, tokens and raw traffic payloads are never written (SEC-09).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import AuditOutcome
from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import INETVariant, JSONVariant
from app.models._checks import in_values


class AuditLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INETVariant, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default=AuditOutcome.SUCCESS.value)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)

    __table_args__ = (
        in_values("outcome", AuditOutcome, "outcome_valid"),
        Index("ix_audit_logs_actor_user_id_created_at", "actor_user_id", text("created_at DESC")),
        Index("ix_audit_logs_action_created_at", "action", text("created_at DESC")),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_created_at", text("created_at DESC")),
    )
