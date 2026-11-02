"""Helpers to build CHECK constraints from the controlled vocabularies."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from sqlalchemy import CheckConstraint


def in_values(column: str, values: Iterable[StrEnum | str], name: str) -> CheckConstraint:
    """``CHECK (column IN (...))`` with values quoted from a trusted enum (never user input)."""
    quoted = ", ".join(f"'{str(value)}'" for value in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)
