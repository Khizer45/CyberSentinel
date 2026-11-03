"""``analysis_jobs`` table (ERD 4.4).

``risk_policy_version`` records which versioned risk policy produced the job's risk scores
(ERD 10, NFR-04). ``updated_at`` doubles as the worker heartbeat used for stale-job recovery.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import JobStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import JSONVariant, UTCDateTime
from app.ml.constants import AnalysisMode
from app.models._checks import in_values


class AnalysisJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_jobs"

    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="RESTRICT"), nullable=False)
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    model_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=JobStatus.QUEUED.value)
    requested_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    input_rows: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    processed_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    risk_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    # Safe, machine-readable code and a short safe message; never a stack trace.
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    dataset = relationship("Dataset", lazy="joined")
    model_version = relationship("ModelVersion", lazy="joined")
    submitter = relationship("User", foreign_keys=[submitted_by], lazy="joined")

    __table_args__ = (
        in_values("status", JobStatus, "status_valid"),
        in_values("requested_mode", AnalysisMode, "requested_mode_valid"),
        CheckConstraint("input_rows IS NULL OR input_rows >= 0", name="input_rows_nonnegative"),
        CheckConstraint("processed_rows >= 0", name="processed_rows_nonnegative"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="completed_after_started",
        ),
        Index("ix_analysis_jobs_submitted_by_created_at", "submitted_by", text("created_at DESC")),
        Index("ix_analysis_jobs_status_created_at", "status", text("created_at DESC")),
        Index("ix_analysis_jobs_dataset_id", "dataset_id"),
        Index("ix_analysis_jobs_model_version_id", "model_version_id"),
    )
