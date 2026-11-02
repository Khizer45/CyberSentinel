"""Alert queue (FR-16): predictions flagged by the risk policy, with status derived from reviews."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.api.deps import AnalystUser, ClientIP, DbSession, Pagination, SettingsDep, as_utc, rate_limit
from app.core.constants import AlertStatus, AuditAction
from app.ml.constants import RiskBand
from app.repositories.base import count_rows
from app.schemas.alert import AlertRead
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.prediction import PredictionDetail
from app.services import alert_service, audit_service, report_service

router = APIRouter(prefix="/alerts", tags=["alerts"], responses=ERROR_RESPONSES)
AlertSort = Literal["created_at", "-created_at", "risk_score", "-risk_score", "record_index", "-record_index"]


class AlertFilters:
    def __init__(
        self,
        severity: Annotated[list[RiskBand] | None, Query(description="Risk band(s)")] = None,
        status: Annotated[list[AlertStatus] | None, Query()] = None,
        label: Annotated[list[str] | None, Query(max_length=20)] = None,
        analysis_job_id: uuid.UUID | None = None,
        dataset_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        ip: Annotated[str | None, Query(max_length=45, description="Matches pseudonymized source/destination IP")] = None,
    ) -> None:
        self.values: dict[str, Any] = {
            "severity": [s.value for s in severity] if severity else None,
            "status": [s.value for s in status] if status else None,
            "label": label,
            "analysis_job_id": analysis_job_id,
            "dataset_id": dataset_id,
            "date_from": as_utc(date_from),
            "date_to": as_utc(date_to),
            "ip": ip,
        }


@router.get("", response_model=Page[AlertRead])
def list_alerts(
    user: AnalystUser,
    db: DbSession,
    settings: SettingsDep,
    page: Pagination,
    filters: Annotated[AlertFilters, Depends()],
    sort: AlertSort = "-created_at",
) -> Page[AlertRead]:
    statement = alert_service.alerts_statement(settings, user, **filters.values)
    items, total = alert_service.list_alerts(db, statement, sort=sort, limit=page.limit, offset=page.offset)
    return Page[AlertRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/export",
    dependencies=[Depends(rate_limit("export", "rate_limit_export", "user"))],
    responses={200: {"content": {"text/csv": {}, "application/json": {}}, "description": "Streamed export"}},
)
def export_alerts(
    user: AnalystUser,
    db: DbSession,
    settings: SettingsDep,
    ip: ClientIP,
    filters: Annotated[AlertFilters, Depends()],
    format: Literal["csv", "json"] = "csv",
) -> StreamingResponse:
    statement = alert_service.alerts_statement(settings, user, **filters.values)
    total = count_rows(db, statement)
    audit_service.record(
        db,
        AuditAction.EXPORT_ALERTS,
        actor_id=user.id,
        ip_address=ip,
        resource_type="alert",
        details={"format": format, "rows": min(total, settings.export_max_rows)},
    )
    db.commit()
    headers = {
        "Content-Disposition": f'attachment; filename="cybersentinel-alerts.{format}"',
        "X-Export-Truncated": "true" if total > settings.export_max_rows else "false",
    }
    return StreamingResponse(
        report_service.alert_export_stream(statement, fmt=format, max_rows=settings.export_max_rows),
        media_type="text/csv" if format == "csv" else "application/json",
        headers=headers,
    )


@router.get("/{alert_id}", response_model=PredictionDetail)
def get_alert(alert_id: uuid.UUID, user: AnalystUser, db: DbSession) -> PredictionDetail:
    return alert_service.get_alert(db, user, alert_id)
