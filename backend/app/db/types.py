"""Portable column types.

Production runs on PostgreSQL (UUID, TIMESTAMPTZ, JSONB, INET). The automated test-suite can also
run on SQLite, so each PostgreSQL-specific type has a portable fallback via ``with_variant``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Timezone-aware current UTC time (ERD 7: store UTC)."""
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """``TIMESTAMPTZ`` that always returns timezone-aware UTC datetimes.

    Naive datetimes are rejected on write to prevent silent local-time bugs.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed; use timezone-aware UTC values")
        value = value.astimezone(UTC)
        if dialect.name == "sqlite":
            # SQLite has no timezone support: store naive UTC so lexical ordering stays correct.
            return value.replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


# JSONB on PostgreSQL, JSON elsewhere (tests).
JSONVariant: Any = JSON().with_variant(JSONB(), "postgresql")

# INET on PostgreSQL, VARCHAR(45) elsewhere (max textual IPv6 length).
INETVariant: Any = String(45).with_variant(INET(), "postgresql")


def score_numeric(precision: int, scale: int) -> Numeric[float]:
    """``NUMERIC(precision, scale)`` returned as ``float`` (exact storage, convenient arithmetic)."""
    return Numeric(precision, scale, asdecimal=False)
