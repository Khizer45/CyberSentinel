import uuid
from datetime import datetime
from typing import Any

from app.core.constants import AuditOutcome
from app.schemas.common import ApiModel
from app.schemas.user import UserRef


class AuditLogRead(ApiModel):
    id: uuid.UUID
    actor: UserRef | None
    action: str
    resource_type: str | None
    resource_id: uuid.UUID | None
    request_id: str | None
    ip_address: str | None
    outcome: AuditOutcome
    details: dict[str, Any] | None
    created_at: datetime
