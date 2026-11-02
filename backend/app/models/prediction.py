"""``predictions`` table (ERD 4.5).

Score semantics (FR-13, ML-07):

* ``probability`` — calibrated P(malicious); populated **only** when the bundle manifest declares that
  calibration was evaluated. Otherwise NULL.
* ``classifier_score`` — raw, uncalibrated attack score from the classifier in [0, 1]
  (ERD 10: "otherwise store a raw score separately").
* ``anomaly_score`` — Isolation Forest abnormality, ``-score_samples(x)``; higher = more anomalous.
* ``risk_score`` / ``risk_band`` — policy outputs (0–100), not probabilities; the policy version is
  stored on the parent job.
* ``true_label`` — ground truth copied from the uploaded dataset when present; used **only** for
  evaluation summaries and never passed to the model.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import JSONVariant, score_numeric
from app.ml.constants import RiskBand
from app.models._checks import in_values


class Prediction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "predictions"

    analysis_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="RESTRICT"), nullable=False)
    record_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    predicted_label: Mapped[str] = mapped_column(String(100), nullable=False)
    probability: Mapped[float | None] = mapped_column(score_numeric(8, 7), nullable=True)
    classifier_score: Mapped[float | None] = mapped_column(score_numeric(8, 7), nullable=True)
    anomaly_score: Mapped[float | None] = mapped_column(score_numeric(12, 8), nullable=True)
    is_anomaly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    risk_score: Mapped[float | None] = mapped_column(score_numeric(6, 2), nullable=True)
    risk_band: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    true_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    flow_context: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)

    job = relationship("AnalysisJob", lazy="raise")

    __table_args__ = (
        UniqueConstraint("analysis_job_id", "record_index"),
        in_values("risk_band", RiskBand, "risk_band_valid"),
        CheckConstraint("record_index >= 0", name="record_index_nonnegative"),
        CheckConstraint("probability IS NULL OR (probability >= 0 AND probability <= 1)", name="probability_range"),
        CheckConstraint(
            "classifier_score IS NULL OR (classifier_score >= 0 AND classifier_score <= 1)",
            name="classifier_score_range",
        ),
        CheckConstraint("risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100)", name="risk_score_range"),
        Index("ix_predictions_analysis_job_id_risk_band", "analysis_job_id", "risk_band"),
        Index("ix_predictions_predicted_label", "predicted_label"),
        # Partial index serving the alert queue (PostgreSQL); a plain index elsewhere.
        Index("ix_predictions_alerts_created_at", text("created_at DESC"), postgresql_where=text("is_alert")),
        Index("ix_predictions_created_at", "created_at"),
    )
