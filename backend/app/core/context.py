"""Per-request / per-job context propagated to logs and audit events via ``contextvars``."""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)


def current_request_id() -> str | None:
    return request_id_var.get()
