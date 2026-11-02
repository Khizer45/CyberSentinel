"""``datasets`` table (ERD 4.2) with soft-deletion and validation-report extensions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, BigInteger, Boolean, CheckConstraint, ForeignKey, Index, String, Text, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DatasetSourceType, DatasetStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import JSONVariant, UTCDateTime
from app.models._checks import in_values


class Dataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "datasets"

    # Nullable only for system-imported datasets (enforced by ck_datasets_owner_required_for_upload).
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Display metadata only, sanitized; never used to build a storage path.
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Opaque internal key; filesystem paths are never exposed through the API.
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    has_ground_truth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    # Bounded summary of validation (counts, warnings, errors); never raw rows.
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DatasetStatus.PENDING.value)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    owner = relationship("User", foreign_keys=[owner_user_id], lazy="joined")

    __table_args__ = (
        in_values("source_type", DatasetSourceType, "source_type_valid"),
        in_values("status", DatasetStatus, "status_valid"),
        CheckConstraint("row_count IS NULL OR row_count >= 0", name="row_count_nonnegative"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_bytes_nonnegative"),
        CheckConstraint("sha256 IS NULL OR length(sha256) = 64", name="sha256_length"),
        CheckConstraint(
            "owner_user_id IS NOT NULL OR source_type <> 'upload'", name="owner_required_for_upload"
        ),
        Index("ix_datasets_owner_user_id_created_at", "owner_user_id", text("created_at DESC")),
        Index("ix_datasets_sha256", "sha256", postgresql_where=text("sha256 IS NOT NULL")),
        Index("ix_datasets_status", "status"),
    )
