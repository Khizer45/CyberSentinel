"""Dashboard metrics (FR-12). Organization-wide aggregates over completed jobs (see role matrix)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.ml.constants import BENIGN_LABEL, NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL
from app.models import Prediction
from app.repositories import analysis_jobs as job_repo
from app.repositories import datasets as dataset_repo
from app.repositories import metrics as metrics_repo
from app.repositories import model_versions as model_repo
from app.schemas.metrics import MetricsSummary, MetricsWindow, ModelMetricsRead, TrendPoint, TrendsResponse


def summary(session: Session, *, date_from: datetime | None, date_to: datetime | None) -> MetricsSummary:
    labels = metrics_repo.grouped_counts(session, Prediction.predicted_label, date_from, date_to)
    bands = metrics_repo.grouped_counts(session, Prediction.risk_band, date_from, date_to)
    total = sum(labels.values())
    special = {BENIGN_LABEL, NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL}
    jobs = job_repo.status_counts(session)
    return MetricsSummary(
        window=MetricsWindow(date_from=date_from, date_to=date_to),
        total_records=total,
        benign_count=labels.get(BENIGN_LABEL, 0),
        malicious_count=sum(n for label, n in labels.items() if label not in special),
        needs_review_count=labels.get(NEEDS_REVIEW_LABEL, 0),
        unclassified_count=labels.get(UNCLASSIFIED_LABEL, 0),
        anomaly_count=metrics_repo.count_where(session, Prediction.is_anomaly.is_(True), date_from, date_to),
        alert_count=metrics_repo.count_where(session, Prediction.is_alert.is_(True), date_from, date_to),
        open_alert_count=metrics_repo.open_alert_count(session, date_from, date_to),
        high_risk_count=bands.get("high", 0) + bands.get("critical", 0),
        label_distribution=labels,
        risk_band_distribution=bands,
        jobs_by_status=jobs,
        completed_jobs=jobs.get("completed", 0),
        active_datasets=dataset_repo.count_active(session),
        approved_models=model_repo.count_approved(session),
    )


def trends(session: Session, *, bucket: str, date_from: datetime | None, date_to: datetime | None) -> TrendsResponse:
    points = metrics_repo.trends(session, bucket, date_from, date_to)
    return TrendsResponse(bucket=bucket, points=[TrendPoint(**p) for p in points])  # type: ignore[arg-type]


def model_metrics(session: Session, *, include_all: bool, family: str | None) -> list[ModelMetricsRead]:
    statuses = None if include_all else ["approved"]
    return [
        ModelMetricsRead(
            model_version_id=m.id,
            model_name=m.model_name,
            version=m.version,
            dataset_family=m.dataset_family,
            status=m.status,
            metrics=m.metrics,
        )
        for m in model_repo.list_models(session, statuses=statuses, family=family)
    ]
