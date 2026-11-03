"""Repository helpers. All queries use SQLAlchemy expressions with bound parameters (SEC-03)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session

from app.core.errors import BadRequestError

T = TypeVar("T")


def count_rows(session: Session, stmt: Select[Any]) -> int:
    return int(session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)


def paginate_scalars(session: Session, stmt: Select[Any], *, limit: int, offset: int) -> tuple[Sequence[Any], int]:
    total = count_rows(session, stmt)
    items = session.scalars(stmt.limit(limit).offset(offset)).unique().all()
    return items, total


def paginate_rows(session: Session, stmt: Select[Any], *, limit: int, offset: int) -> tuple[Sequence[Any], int]:
    total = count_rows(session, stmt)
    rows = session.execute(stmt.limit(limit).offset(offset)).all()
    return rows, total


def order_by_allowlisted(sort: str, allowed: Mapping[str, Any]) -> list[ColumnElement[Any]]:
    """Translate ``"-created_at"`` into an ORDER BY clause using only allowlisted columns."""
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    column = allowed.get(key)
    if column is None:
        raise BadRequestError("unsupported sort field", details={"allowed": sorted(allowed)})
    return [column.desc() if descending else column.asc()]
