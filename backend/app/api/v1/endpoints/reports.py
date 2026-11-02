"""Downloadable summary reports (PRD US4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response

from app.api.deps import AnyUser, ClientIP, DbSession, SettingsDep, as_utc, rate_limit
from app.core.constants import AuditAction
from app.schemas.common import ERROR_RESPONSES
from app.schemas.report import SummaryReport
from app.services import audit_service, report_service

router = APIRouter(prefix="/reports", tags=["reports"], responses=ERROR_RESPONSES)


@router.get(
    "/summary",
    response_model=SummaryReport,
    dependencies=[Depends(rate_limit("export", "rate_limit_export", "user"))],
    responses={200: {"content": {"application/json": {}, "text/csv": {}}}},
)
def summary_report(
    user: AnyUser,
    db: DbSession,
    settings: SettingsDep,
    ip: ClientIP,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    format: Literal["json", "csv"] = "json",
) -> object:
    """Organization-wide aggregate report (no record-level data), as JSON or CSV."""
    report = report_service.summary_report(db, settings, user=user, date_from=as_utc(date_from), date_to=as_utc(date_to))
    audit_service.record(
        db, AuditAction.EXPORT_REPORT, actor_id=user.id, ip_address=ip, resource_type="report", details={"format": format}
    )
    db.commit()
    if format == "csv":
        return Response(
            report_service.summary_report_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="cybersentinel-summary.csv"'},
        )
    return SummaryReport(**report)
