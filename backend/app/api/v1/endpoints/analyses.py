"""Analysis jobs and their predictions (FR-07, FR-09, FR-10, FR-11) plus result exports."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import AnalystUser, ClientIP, DbSession, Pagination, Registry, Risk, Runner, SettingsDep, rate_limit
from app.core.constants import AuditAction, JobStatus
from app.core.errors import ConflictError
from app.ml.constants import RiskBand
from app.models import AnalysisJob, Prediction
from app.repositories import analysis_jobs as job_repo
from app.repositories import predictions as prediction_repo
from app.repositories.base import count_rows
from app.schemas.analysis import AnalysisCreate, AnalysisJobRead
from app.schemas.common import ERROR_RESPONSES, ErrorResponse, Page
from app.schemas.prediction import PredictionRead
from app.services import analysis_service, audit_service, report_service

router = APIRouter(prefix="/analyses", tags=["analyses"], responses=ERROR_RESPONSES)
JobSort = Literal["created_at", "-created_at", "completed_at", "-completed_at", "status", "-status"]
PredictionSort = Literal[
    "record_index",
    "-record_index",
    "risk_score",
    "-risk_score",
    "anomaly_score",
    "-anomaly_score",
    "classifier_score",
    "-classifier_score",
]


@router.post(
    "",
    response_model=AnalysisJobRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("analysis", "rate_limit_analysis", "user"))],
    responses={
        409: {"model": ErrorResponse, "description": "Dataset not validated or model not approved"},
        422: {"model": ErrorResponse, "description": "Dataset schema incompatible with the model or unsupported mode"},
        503: {"model": ErrorResponse, "description": "Model artifact unavailable or analysis queue full"},
    },
)
def create_analysis(
    payload: AnalysisCreate,
    response: Response,
    user: AnalystUser,
    db: DbSession,
    registry: Registry,
    runner: Runner,
    risk: Risk,
    ip: ClientIP,
) -> AnalysisJob:
    """Queue an asynchronous analysis job; poll ``GET /analyses/{id}`` for progress."""
    job = analysis_service.create_job(db, user=user, payload=payload, registry=registry, runner=runner, risk=risk, ip=ip)
    response.headers["Location"] = f"/api/v1/analyses/{job.id}"
    return job


@router.get("", response_model=Page[AnalysisJobRead])
def list_analyses(
    user: AnalystUser,
    db: DbSession,
    page: Pagination,
    status_filter: Annotated[JobStatus | None, Query(alias="status")] = None,
    dataset_id: uuid.UUID | None = None,
    model_version_id: uuid.UUID | None = None,
    sort: JobSort = "-created_at",
) -> Page[AnalysisJobRead]:
    items, total = job_repo.list_jobs(
        db,
        user,
        status=status_filter,
        dataset_id=dataset_id,
        model_version_id=model_version_id,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[AnalysisJobRead](
        items=[AnalysisJobRead.model_validate(j) for j in items], total=total, limit=page.limit, offset=page.offset
    )


@router.get("/{job_id}", response_model=AnalysisJobRead)
def get_analysis(job_id: uuid.UUID, user: AnalystUser, db: DbSession) -> AnalysisJob:
    return analysis_service.get_job(db, user, job_id)


@router.post("/{job_id}/cancel", response_model=AnalysisJobRead)
def cancel_analysis(job_id: uuid.UUID, user: AnalystUser, db: DbSession, ip: ClientIP) -> AnalysisJob:
    return analysis_service.cancel_job(db, user=user, job_id=job_id, ip=ip)


@router.get("/{job_id}/predictions", response_model=Page[PredictionRead])
def list_predictions(
    job_id: uuid.UUID,
    user: AnalystUser,
    db: DbSession,
    page: Pagination,
    label: Annotated[list[str] | None, Query(max_length=20)] = None,
    risk_band: Annotated[list[RiskBand] | None, Query()] = None,
    is_anomaly: bool | None = None,
    is_alert: bool | None = None,
    min_risk: Annotated[float | None, Query(ge=0, le=100)] = None,
    max_risk: Annotated[float | None, Query(ge=0, le=100)] = None,
    sort: PredictionSort = "record_index",
) -> Page[PredictionRead]:
    job = analysis_service.get_job(db, user, job_id)
    items, total = prediction_repo.list_for_job(
        db,
        job.id,
        labels=label,
        risk_bands=[b.value for b in risk_band] if risk_band else None,
        is_anomaly=is_anomaly,
        is_alert=is_alert,
        min_risk=min_risk,
        max_risk=max_risk,
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[PredictionRead](
        items=[PredictionRead.model_validate(p) for p in items], total=total, limit=page.limit, offset=page.offset
    )


@router.get(
    "/{job_id}/export",
    dependencies=[Depends(rate_limit("export", "rate_limit_export", "user"))],
    responses={200: {"content": {"text/csv": {}, "application/json": {}}, "description": "Streamed export"}},
)
def export_predictions(
    job_id: uuid.UUID,
    user: AnalystUser,
    db: DbSession,
    settings: SettingsDep,
    ip: ClientIP,
    format: Literal["csv", "json"] = "csv",
    label: Annotated[list[str] | None, Query(max_length=20)] = None,
    risk_band: Annotated[list[RiskBand] | None, Query()] = None,
    is_anomaly: bool | None = None,
    is_alert: bool | None = None,
    min_risk: Annotated[float | None, Query(ge=0, le=100)] = None,
    max_risk: Annotated[float | None, Query(ge=0, le=100)] = None,
) -> StreamingResponse:
    """Export (filtered) predictions of a completed job. Capped at ``EXPORT_MAX_ROWS``; cells are formula-escaped."""
    job = analysis_service.get_job(db, user, job_id)
    if job.status != JobStatus.COMPLETED:
        raise ConflictError("Only completed jobs can be exported.", code="job_not_completed")
    filters: dict[str, Any] = {
        "labels": label,
        "risk_bands": [b.value for b in risk_band] if risk_band else None,
        "is_anomaly": is_anomaly,
        "is_alert": is_alert,
        "min_risk": min_risk,
        "max_risk": max_risk,
    }
    total = count_rows(
        db, prediction_repo.apply_prediction_filters(select(Prediction).where(Prediction.analysis_job_id == job.id), **filters)
    )
    audit_service.record(
        db,
        AuditAction.EXPORT_PREDICTIONS,
        actor_id=user.id,
        ip_address=ip,
        resource_type="analysis_job",
        resource_id=job.id,
        details={"format": format, "rows": min(total, settings.export_max_rows)},
    )
    db.commit()
    media = "text/csv" if format == "csv" else "application/json"
    headers = {
        "Content-Disposition": f'attachment; filename="cybersentinel-analysis-{job.id}.{format}"',
        "X-Export-Truncated": "true" if total > settings.export_max_rows else "false",
    }
    stream = report_service.prediction_export_stream(job, filters, fmt=format, max_rows=settings.export_max_rows)
    return StreamingResponse(stream, media_type=media, headers=headers)
