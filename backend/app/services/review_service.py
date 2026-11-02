"""Append-only analyst reviews of predictions/alerts (FR-15)."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from app.core.constants import AuditAction, JobStatus
from app.core.errors import ConflictError
from app.models import AlertReview, User
from app.schemas.review import ReviewCreate
from app.services import audit_service
from app.services.prediction_service import get_visible

_CONTROL_EXCEPT_NEWLINE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_notes(notes: str | None) -> str | None:
    if notes is None:
        return None
    text = _CONTROL_EXCEPT_NEWLINE.sub(" ", notes).strip()
    return text or None


def add_review(session: Session, *, user: User, prediction_id: uuid.UUID, payload: ReviewCreate, ip: str | None) -> AlertReview:
    prediction, job = get_visible(session, user, prediction_id)
    if job.status != JobStatus.COMPLETED:
        raise ConflictError("Predictions can only be reviewed after the analysis job has completed.", code="job_not_completed")
    review = AlertReview(
        prediction_id=prediction.id,
        reviewed_by=user.id,
        disposition=payload.disposition.value,
        notes=clean_notes(payload.notes),
    )
    session.add(review)
    session.flush()
    audit_service.record(
        session,
        AuditAction.ALERT_REVIEW,
        actor_id=user.id,
        ip_address=ip,
        resource_type="prediction",
        resource_id=prediction.id,
        details={"disposition": review.disposition, "risk_band": prediction.risk_band, "has_notes": review.notes is not None},
    )
    session.commit()
    session.refresh(review)
    return review
