"""HTTP middleware: correlation IDs and access logs, security headers, request body size limits.

All three are pure ASGI middleware (no ``BaseHTTPMiddleware``) so that streaming responses and uploads
are not buffered.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from app.core.context import request_id_var, user_id_var
from app.core.errors import RequestTooLarge, error_body

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

access_logger = logging.getLogger("cybersentinel.access")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,80}$")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key.lower() == name:
            return value.decode("latin-1")
    return None


class RequestContextMiddleware:
    """Assigns/propagates ``X-Request-ID`` and writes one structured access-log line per request.

    The query string is not logged (it may contain filter values such as IP addresses).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = _header(scope, b"x-request-id")
        request_id = incoming if incoming and _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        user_token = user_id_var.set(None)
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            access_logger.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_holder["status"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            request_id_var.reset(token)
            user_id_var.reset(user_token)


class SecurityHeadersMiddleware:
    """Adds defensive headers. API responses get a deny-all CSP; the Swagger UI path gets a relaxed one."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False, docs_prefix: str = "/api/docs") -> None:
        self.app = app
        self.hsts = hsts
        self.docs_prefix = docs_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        is_docs = path.startswith(self.docs_prefix)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {k.lower() for k, _ in headers}

                def add(name: str, value: str) -> None:
                    if name.encode() not in existing:
                        headers.append((name.encode(), value.encode()))

                add("x-content-type-options", "nosniff")
                add("x-frame-options", "DENY")
                add("referrer-policy", "no-referrer")
                add("cross-origin-opener-policy", "same-origin")
                add("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=()")
                if is_docs:
                    add(
                        "content-security-policy",
                        "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                        "img-src 'self' data: https://fastapi.tiangolo.com; "
                        "frame-ancestors 'none'",
                    )
                else:
                    add("content-security-policy", "default-src 'none'; frame-ancestors 'none'")
                    add("cache-control", "no-store")
                if self.hsts:
                    add("strict-transport-security", "max-age=31536000; includeSubDomains")
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class BodySizeLimitMiddleware:
    """Rejects bodies above the limit *while streaming* (Content-Length is checked first but not trusted).

    ``upload_paths`` (exact path prefixes) get the upload limit; everything else gets the JSON limit.
    """

    def __init__(self, app: ASGIApp, *, default_limit: int, upload_limit: int, upload_paths: tuple[str, ...]) -> None:
        self.app = app
        self.default_limit = default_limit
        self.upload_limit = upload_limit
        self.upload_paths = upload_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        limit = self.upload_limit if any(path == p or path.startswith(p + "/") for p in self.upload_paths) else self.default_limit
        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > limit
            except ValueError:
                too_big = True
            if too_big:
                await self._reject(send)
                return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLarge()
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = json.dumps(error_body("payload_too_large", "The request body exceeds the configured size limit.")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            }
        )
        await send({"type": "http.response.body", "body": body})
