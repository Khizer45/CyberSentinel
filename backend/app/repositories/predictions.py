"""Predictions, derived alerts and append-only reviews."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, Select, delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import CLOSING_DISPOSITIONS, AlertStatus, Disposition, JobStatus, UserRole
from app.models import AlertReview, AnalysisJob, Dataset, ModelVersion, Prediction, User
from app.repositories.base import order_by_allowlisted, paginate_rows, paginate_scalars

PREDICTION_SORTS = {
    "record_index": Prediction.record_index,
    "risk_score": Prediction.risk_score,
    "anomaly_score": Prediction.anomaly_score,
    "classifier_score": Prediction.classifier_score,
}
ALERT_SORTS = {"created_at": Prediction.created_at, "risk_score": Prediction.risk_score, "record_index": Prediction.record_index}


def _latest_disposition() -> Any:
    return (
        select(AlertReview.disposition)
        .where(AlertReview.prediction_id == Prediction.id)
        .order_by(AlertReview.created_at.desc(), AlertReview.id.desc())
        .limit(1)
        .correlate(Prediction)
        .scalar_subquery()
    )


def _review_count() -> Any:
    return (
        select(func.count(AlertReview.id))
        .where(AlertReview.prediction_id == Prediction.id)
        .correlate(Prediction)
        .scalar_subquery()
    )


def status_from_disposition(disposition: str | None) -> AlertStatus:
    if disposition is None:
        return AlertStatus.OPEN
    if disposition == Disposition.NEEDS_INVESTIGATION:
        return AlertStatus.INVESTIGATING
    return AlertStatus.CLOSED


def _visible_jobs(stmt: Select, user: User) -> Select:  # type: ignore[type-arg]
    return stmt if user.role == UserRole.ADMIN else stmt.where(AnalysisJob.submitted_by == user.id)


def get_visible_prediction(session: Session, prediction_id: uuid.UUID, user: User) -> tuple[Prediction, AnalysisJob] | None:
    stmt: Select[*tuple[Any, ...]] = select(Prediction, AnalysisJob).join(
        AnalysisJob, Prediction.analysis_job_id == AnalysisJob.id
    )
    row = session.execute(_visible_jobs(stmt, user).where(Prediction.id == prediction_id)).unique().first()
    return (row[0], row[1]) if row else None


def list_for_job(
    session: Session,
    job_id: uuid.UUID,
    *,
    labels: Sequence[str] | None,
    risk_bands: Sequence[str] | None,
    is_anomaly: bool | None,
    is_alert: bool | None,
    min_risk: float | None,
    max_risk: float | None,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[Sequence[Prediction], int]:
    stmt = select(Prediction).where(Prediction.analysis_job_id == job_id)
    stmt = apply_prediction_filters(stmt, labels, risk_bands, is_anomaly, is_alert, min_risk, max_risk)
    stmt = stmt.order_by(*order_by_allowlisted(sort, PREDICTION_SORTS), Prediction.record_index)
    return paginate_scalars(session, stmt, limit=limit, offset=offset)


def apply_prediction_filters(
    stmt: Select,  # type: ignore[type-arg]
    labels: Sequence[str] | None,
    risk_bands: Sequence[str] | None,
    is_anomaly: bool | None,
    is_alert: bool | None,
    min_risk: float | None,
    max_risk: float | None,
) -> Select:  # type: ignore[type-arg]
    if labels:
        stmt = stmt.where(Prediction.predicted_label.in_(list(labels)))
    if risk_bands:
        stmt = stmt.where(Prediction.risk_band.in_(list(risk_bands)))
    if is_anomaly is not None:
        stmt = stmt.where(Prediction.is_anomaly.is_(is_anomaly))
    if is_alert is not None:
        stmt = stmt.where(Prediction.is_alert.is_(is_alert))
    if min_risk is not None:
        stmt = stmt.where(Prediction.risk_score >= min_risk)
    if max_risk is not None:
        stmt = stmt.where(Prediction.risk_score <= max_risk)
    return stmt


def alerts_query(
    user: User,
    *,
    risk_bands: Sequence[str] | None = None,
    statuses: Sequence[str] | None = None,
    labels: Sequence[str] | None = None,
    job_id: uuid.UUID | None = None,
    dataset_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    ip_pseudonym: str | None = None,
) -> Select:  # type: ignore[type-arg]
    latest = _latest_disposition()
    stmt: Select[*tuple[Any, ...]] = (
        select(
            Prediction.id.label("id"),
            Prediction.analysis_job_id,
            AnalysisJob.dataset_id,
            Dataset.name.label("dataset_name"),
            ModelVersion.model_name,
            ModelVersion.version.label("model_version"),
            Prediction.record_index,
            Prediction.predicted_label,
            Prediction.risk_score,
            Prediction.risk_band,
            Prediction.anomaly_score,
            Prediction.is_anomaly,
            Prediction.classifier_score,
            Prediction.probability,
            Prediction.created_at,
            latest.label("latest_disposition"),
            _review_count().label("review_count"),
        )
        .join(AnalysisJob, Prediction.analysis_job_id == AnalysisJob.id)
        .join(Dataset, AnalysisJob.dataset_id == Dataset.id)
        .join(ModelVersion, AnalysisJob.model_version_id == ModelVersion.id)
        .where(Prediction.is_alert.is_(True), AnalysisJob.status == JobStatus.COMPLETED)
    )
    stmt = _visible_jobs(stmt, user)
    if risk_bands:
        stmt = stmt.where(Prediction.risk_band.in_(list(risk_bands)))
    if labels:
        stmt = stmt.where(Prediction.predicted_label.in_(list(labels)))
    if job_id:
        stmt = stmt.where(Prediction.analysis_job_id == job_id)
    if dataset_id:
        stmt = stmt.where(AnalysisJob.dataset_id == dataset_id)
    if date_from:
        stmt = stmt.where(Prediction.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Prediction.created_at <= date_to)
    if ip_pseudonym:
        stmt = stmt.where(
            or_(
                Prediction.flow_context["src_ip"].as_string() == ip_pseudonym,
                Prediction.flow_context["dst_ip"].as_string() == ip_pseudonym,
            )
        )
    if statuses:
        conditions = []
        if AlertStatus.OPEN in statuses:
            conditions.append(latest.is_(None))
        if AlertStatus.INVESTIGATING in statuses:
            conditions.append(latest == Disposition.NEEDS_INVESTIGATION.value)
        if AlertStatus.CLOSED in statuses:
            conditions.append(latest.in_([d.value for d in CLOSING_DISPOSITIONS]))
        stmt = stmt.where(or_(*conditions))
    return stmt


def list_alerts(session: Session, stmt: Select, *, sort: str, limit: int, offset: int) -> tuple[Sequence[Any], int]:  # type: ignore[type-arg]
    stmt = stmt.order_by(*order_by_allowlisted(sort, ALERT_SORTS), Prediction.id)
    return paginate_rows(session, stmt, limit=limit, offset=offset)


def reviews_for(session: Session, prediction_id: uuid.UUID) -> Sequence[AlertReview]:
    return session.scalars(
        select(AlertReview)
        .where(AlertReview.prediction_id == prediction_id)
        .order_by(AlertReview.created_at.desc(), AlertReview.id.desc())
    ).all()


def iter_job_predictions(session: Session, job_id: uuid.UUID, filters: dict[str, Any], *, batch: int = 1000, max_rows: int):
    """Keyset pagination by record_index for streaming exports."""
    last = -1
    produced = 0
    while produced < max_rows:
        stmt = select(Prediction).where(Prediction.analysis_job_id == job_id, Prediction.record_index > last)
        stmt = apply_prediction_filters(stmt, **filters)
        rows = session.scalars(stmt.order_by(Prediction.record_index).limit(min(batch, max_rows - produced))).all()
        if not rows:
            return
        yield rows
        produced += len(rows)
        last = rows[-1].record_index


def alert_counts_by_status(session: Session, *, date_from: datetime | None, date_to: datetime | None) -> dict[str, int]:
    latest = _latest_disposition()
    stmt: Select[*tuple[Any, ...]] = (
        select(latest.label("disposition"), func.count())
        .select_from(Prediction)
        .join(AnalysisJob, Prediction.analysis_job_id == AnalysisJob.id)
        .where(Prediction.is_alert.is_(True), AnalysisJob.status == JobStatus.COMPLETED)
    )
    if date_from:
        stmt = stmt.where(Prediction.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Prediction.created_at <= date_to)
    rows = session.execute(stmt.group_by(latest)).all()
    return {str(disposition) if disposition else "unreviewed": int(count) for disposition, count in rows}


def delete_for_job(session: Session, job_id: uuid.UUID) -> int:
    """Remove partial predictions of a failed/cancelled job (never called for completed jobs)."""
    result = session.execute(
        delete(Prediction)
        .where(Prediction.analysis_job_id == job_id, ~Prediction.id.in_(select(AlertReview.prediction_id)))
        .execution_options(synchronize_session=False)
    )
    return int(cast(CursorResult[Any], result).rowcount or 0)
