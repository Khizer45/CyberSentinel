"""``model_versions`` table (ERD 4.3): registry of trusted, integrity-pinned model bundles.

``artifact_uri`` is a path *relative to MODEL_DIR* and is never returned by the API (FR-06).
``artifact_sha256`` pins the SHA-256 of the bundle's ``manifest.json``; the manifest in turn pins the
SHA-256 of every component file (chain of trust, SEC-06).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, Boolean, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import ModelStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import JSONVariant, UTCDateTime
from app.ml.constants import ModelType
from app.models._checks import in_values


class ModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_versions"

    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    model_type: Mapped[str] = mapped_column(String(40), nullable=False)
    task: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dataset_family: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    preprocessing_version: Mapped[str] = mapped_column(String(60), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(60), nullable=False)
    label_map: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    threshold_config: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    explanation_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    probability_calibrated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ModelStatus.DRAFT.value)
    status_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("model_name", "version"),
        in_values("model_type", ModelType, "model_type_valid"),
        in_values("status", ModelStatus, "status_valid"),
        CheckConstraint("length(artifact_sha256) = 64", name="artifact_sha256_length"),
        Index("ix_model_versions_status", "status"),
    )
