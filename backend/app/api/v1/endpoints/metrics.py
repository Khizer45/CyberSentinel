"""Dashboard metrics (FR-12): organization-wide aggregates; no record-level data."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter

from app.api.deps import AnyUser, DbSession, as_utc
from app.core.constants import UserRole
from app.schemas.common import ERROR_RESPONSES
from app.schemas.metrics import MetricsSummary, ModelMetricsRead, TrendsResponse
from app.services import metrics_service

router = APIRouter(prefix="/metrics", tags=["metrics"], responses=ERROR_RESPONSES)


@router.get("/summary", response_model=MetricsSummary)
def summary(user: AnyUser, db: DbSession, date_from: datetime | None = None, date_to: datetime | None = None) -> MetricsSummary:
    return metrics_service.summary(db, date_from=as_utc(date_from), date_to=as_utc(date_to))


@router.get("/trends", response_model=TrendsResponse)
def trends(
    user: AnyUser,
    db: DbSession,
    bucket: Literal["day", "hour"] = "day",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> TrendsResponse:
    return metrics_service.trends(db, bucket=bucket, date_from=as_utc(date_from), date_to=as_utc(date_to))


@router.get("/models", response_model=list[ModelMetricsRead])
def model_metrics(user: AnyUser, db: DbSession, dataset_family: str | None = None) -> list[ModelMetricsRead]:
    """Measured evaluation metrics recorded in approved model manifests (all statuses for administrators)."""
    return metrics_service.model_metrics(db, include_all=user.role == UserRole.ADMIN, family=dataset_family)
