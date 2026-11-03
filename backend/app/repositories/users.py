from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.models import User
from app.repositories.base import order_by_allowlisted, paginate_scalars
from app.utils.text import escape_like

SORTS = {"created_at": User.created_at, "email": User.email, "display_name": User.display_name, "role": User.role}


def get(session: Session, user_id: uuid.UUID) -> User | None:
    return session.get(User, user_id)


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def list_users(
    session: Session, *, role: str | None, is_active: bool | None, q: str | None, sort: str, limit: int, offset: int
) -> tuple[Sequence[User], int]:
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if q:
        pattern = f"%{escape_like(q.lower())}%"
        stmt = stmt.where(or_(User.email.ilike(pattern, escape="\\"), User.display_name.ilike(pattern, escape="\\")))
    stmt = stmt.order_by(*order_by_allowlisted(sort, SORTS), User.id)
    return paginate_scalars(session, stmt, limit=limit, offset=offset)


def count_active_admins(session: Session) -> int:
    return int(
        session.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))) or 0
    )
