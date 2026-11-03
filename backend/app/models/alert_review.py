"""``alert_reviews`` table (ERD 4.6): append-only analyst dispositions.

The application never updates or deletes reviews; on PostgreSQL a trigger created by the initial
migration rejects UPDATE/DELETE/TRUNCATE so the review history is preserved (FR-15).
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import Disposition
from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models._checks import in_values

REVIEW_NOTES_MAX_LENGTH = 2000


class AlertReview(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "alert_reviews"

    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("predictions.id", ondelete="RESTRICT"), nullable=False)
    reviewed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    disposition: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    reviewer = relationship("User", lazy="joined")

    __table_args__ = (
        in_values("disposition", Disposition, "disposition_valid"),
        CheckConstraint(f"notes IS NULL OR length(notes) <= {REVIEW_NOTES_MAX_LENGTH}", name="notes_length"),
        Index("ix_alert_reviews_prediction_id_created_at", "prediction_id", text("created_at DESC")),
        Index("ix_alert_reviews_reviewed_by", "reviewed_by"),
    )
