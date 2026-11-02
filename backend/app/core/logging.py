"""Structured JSON logging with correlation IDs and secret redaction (NFR-05, SEC-09).

Every record carries ``request_id``, ``user_id`` and ``job_id`` from :mod:`app.core.context`. Values of keys
that look sensitive (passwords, tokens, secrets, cookies, authorization headers) are replaced by ``[REDACTED]``
— callers should never pass such values, this is a safety net.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.context import job_id_var, request_id_var, user_id_var

_SENSITIVE = re.compile(r"pass(word)?|secret|token|authorization|cookie|api[_-]?key|credential", re.IGNORECASE)
_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message", "asctime"}


def redact(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SENSITIVE.search(str(k)) else redact(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, depth + 1) for v in value[:50]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…"
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "job_id": job_id_var.get(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")}
        if extras:
            payload.update(redact(extras))
        if record.exc_info:
            # Stack traces go to the server log only — never to API responses.
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        rid = request_id_var.get()
        return f"{base} [request_id={rid}]" if rid else base


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("uvicorn.access", "multipart", "python_multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
