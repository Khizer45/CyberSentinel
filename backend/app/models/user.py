"""``users`` table (ERD 4.1) plus brute-force and token-revocation fields."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import UserRole
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import UTCDateTime
from app.models._checks import in_values


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), nullable=False)
    # Argon2id hash only; plaintext passwords are never stored (SEC-01).
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    # Extensions: lockout after repeated failures and server-side token revocation.
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("email"),
        in_values("role", UserRole, "role_valid"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("failed_login_attempts >= 0", name="failed_login_attempts_nonnegative"),
        CheckConstraint("token_version >= 0", name="token_version_nonnegative"),
        Index("ix_users_role_is_active", "role", "is_active"),
    )

    def __repr__(self) -> str:  # never include the password hash
        return f"<User id={self.id} role={self.role} active={self.is_active}>"
