"""Audit trail writer (FR-18, SEC-09).

* Success events are written in the caller's session so they commit atomically with the business change.
* Failure/denied events use :func:`record_independent`, which commits in its own session so the event survives
  even when the triggering transaction is rolled back.
* ``details`` is sanitized: sensitive keys are dropped, strings truncated, nesting and total size bounded.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import AuditAction, AuditOutcome
from app.core.context import current_request_id
from app.db.session import get_database
from app.models import AuditLog

logger = logging.getLogger("cybersentinel.audit")
_SENSITIVE = re.compile(r"pass(word)?|secret|token|authorization|cookie|api[_-]?key|hash|credential", re.IGNORECASE)
MAX_DETAILS_BYTES = 4096


def sanitize_details(details: dict[str, Any] | None, depth: int = 0) -> dict[str, Any] | None:
    if not details:
        return None
    clean: dict[str, Any] = {}
    for key, value in list(details.items())[:30]:
        key = str(key)[:60]
        if _SENSITIVE.search(key):
            continue
        if isinstance(value, dict):
            if depth < 2:
                nested = sanitize_details(value, depth + 1)
                if nested is not None:
                    clean[key] = nested
        elif isinstance(value, (list, tuple)):
            clean[key] = [str(v)[:200] if not isinstance(v, (int, float, bool)) else v for v in list(value)[:20]]
        elif isinstance(value, (int, float, bool)) or value is None:
            clean[key] = value
        else:
            clean[key] = str(value)[:500]
    if len(json.dumps(clean, default=str)) > MAX_DETAILS_BYTES:
        return {"truncated": True}
    return clean


def build_entry(
    action: AuditAction | str,
    *,
    actor_id: uuid.UUID | None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    return AuditLog(
        actor_user_id=actor_id,
        action=str(action),
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=current_request_id(),
        ip_address=ip_address,
        outcome=str(outcome),
        details=sanitize_details(details),
    )


def record(session: Session, action: AuditAction | str, **kwargs: Any) -> None:
    """Add an audit entry to ``session`` (committed together with the caller's transaction)."""
    session.add(build_entry(action, **kwargs))


def record_independent(action: AuditAction | str, **kwargs: Any) -> None:
    """Write an audit entry in its own transaction (for failures and denials). Never raises."""
    try:
        with get_database().session() as session:
            session.add(build_entry(action, **kwargs))
            session.commit()
    except Exception:  # pragma: no cover - auditing must not break the request path
        logger.exception("failed to write audit event", extra={"action": str(action)})
