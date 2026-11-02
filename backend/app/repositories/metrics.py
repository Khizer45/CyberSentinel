"""Aggregate queries for dashboards and reports (organization-wide, completed jobs only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, exists, func, select
from sqlalchemy.orm import Session

from app.core.constants import JobStatus
from app.ml.constants import BENIGN_LABEL, NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL
from app.models import AlertReview, AnalysisJob, Prediction

NON_MALICIOUS = (BENIGN_LABEL, NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL)


def _completed(stmt: Select, date_from: datetime | None, date_to: datetime | None) -> Select:  # type: ignore[type-arg]
    stmt = stmt.join(AnalysisJob, Prediction.analysis_job_id == AnalysisJob.id).where(AnalysisJob.status == JobStatus.COMPLETED)
    if date_from:
        stmt = stmt.where(Prediction.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Prediction.created_at <= date_to)
    return stmt


def grouped_counts(session: Session, column: Any, date_from: datetime | None, date_to: datetime | None) -> dict[str, int]:
    stmt = _completed(select(column, func.count()).select_from(Prediction), date_from, date_to).group_by(column)
    return {str(key): int(count) for key, count in session.execute(stmt).all() if key is not None}


def count_where(session: Session, condition: Any, date_from: datetime | None, date_to: datetime | None) -> int:
    stmt = _completed(select(func.count()).select_from(Prediction), date_from, date_to).where(condition)
    return int(session.scalar(stmt) or 0)


def open_alert_count(session: Session, date_from: datetime | None, date_to: datetime | None) -> int:
    reviewed = exists(select(AlertReview.id).where(AlertReview.prediction_id == Prediction.id))
    return count_where(session, Prediction.is_alert.is_(True) & ~reviewed, date_from, date_to)


def _bucket(session: Session, bucket: str) -> Any:
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        truncated = func.date_trunc(bucket, func.timezone("UTC", Prediction.created_at))
        return func.to_char(truncated, "YYYY-MM-DD" if bucket == "day" else 'YYYY-MM-DD"T"HH24":00"')
    return func.strftime("%Y-%m-%d" if bucket == "day" else "%Y-%m-%dT%H:00", Prediction.created_at)


def trends(session: Session, bucket: str, date_from: datetime | None, date_to: datetime | None) -> list[dict[str, Any]]:
    key = _bucket(session, bucket).label("bucket")
    malicious = func.sum(func.cast(~Prediction.predicted_label.in_(NON_MALICIOUS), type_=_int_type()))
    anomalies = func.sum(func.cast(Prediction.is_anomaly.is_(True), type_=_int_type()))
    alerts = func.sum(func.cast(Prediction.is_alert.is_(True), type_=_int_type()))
    stmt = _completed(select(key, func.count(), malicious, anomalies, alerts).select_from(Prediction), date_from, date_to)
    rows = session.execute(stmt.group_by(key).order_by(key)).all()
    return [
        {"bucket": str(b), "records": int(n), "malicious": int(m or 0), "anomalies": int(a or 0), "alerts": int(al or 0)}
        for b, n, m, a, al in rows
    ]


def _int_type() -> Any:
    from sqlalchemy import Integer

    return Integer()
