"""Alert queries (FR-16). Alerts are predictions flagged by the risk policy; status derives from reviews."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models import User
from app.repositories import predictions as prediction_repo
from app.schemas.alert import AlertRead
from app.schemas.prediction import PredictionDetail
from app.services import prediction_service
from app.utils.ip import pseudonymize_ip


def alerts_statement(
    settings: Settings,
    user: User,
    *,
    severity: Sequence[str] | None,
    status: Sequence[str] | None,
    label: Sequence[str] | None,
    analysis_job_id: uuid.UUID | None,
    dataset_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    ip: str | None,
) -> Any:
    pseudonym = None
    if ip:
        key = settings.ip_pseudonymization_key
        pseudonym = pseudonymize_ip(ip, key.get_secret_value().encode() if key else None) or "__no_match__"
    return prediction_repo.alerts_query(
        user,
        risk_bands=severity,
        statuses=status,
        labels=label,
        job_id=analysis_job_id,
        dataset_id=dataset_id,
        date_from=date_from,
        date_to=date_to,
        ip_pseudonym=pseudonym,
    )


def to_alert(row: Any) -> AlertRead:
    data = dict(row._mapping)
    disposition = data.pop("latest_disposition")
    return AlertRead(**data, latest_disposition=disposition, status=prediction_repo.status_from_disposition(disposition))


def list_alerts(session: Session, statement: Any, *, sort: str, limit: int, offset: int) -> tuple[list[AlertRead], int]:
    rows, total = prediction_repo.list_alerts(session, statement, sort=sort, limit=limit, offset=offset)
    return [to_alert(row) for row in rows], total


def get_alert(session: Session, user: User, alert_id: uuid.UUID) -> PredictionDetail:
    prediction, job = prediction_service.get_visible(session, user, alert_id)
    if not prediction.is_alert:
        raise NotFoundError("Alert not found.")
    return prediction_service.build_detail(session, prediction, job)
