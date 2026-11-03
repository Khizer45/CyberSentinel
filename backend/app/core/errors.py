"""Application error hierarchy and the consistent error envelope (NFR-01, Workflow Manual 7.3).

Every error response has the shape::

    {"error": {"code": "<machine_code>", "message": "<safe message>", "details": <optional>, "request_id": "<id>"}}

Stack traces, SQL, file-system paths and secrets are never included. Unexpected exceptions are logged with
their traceback server-side and returned as a generic ``500 internal_error`` with the request ID.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import current_request_id
from app.ml.errors import ArtifactError, InferenceError, MLError

logger = logging.getLogger("cybersentinel.errors")


class AppError(Exception):
    status_code = 500
    code = "internal_error"
    message = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        self.headers = headers


class BadRequestError(AppError):
    status_code, code, message = 400, "bad_request", "The request is invalid."


class AuthenticationError(AppError):
    status_code, code, message = 401, "authentication_required", "Authentication is required."


class InvalidCredentialsError(AuthenticationError):
    code, message = "invalid_credentials", "Invalid email or password."


class PermissionDeniedError(AppError):
    status_code, code, message = 403, "permission_denied", "You do not have permission to perform this action."


class NotFoundError(AppError):
    status_code, code, message = 404, "not_found", "The requested resource was not found."


class ConflictError(AppError):
    status_code, code, message = 409, "conflict", "The request conflicts with the current state of the resource."


class PayloadTooLargeError(AppError):
    status_code, code, message = 413, "payload_too_large", "The request body exceeds the configured size limit."


class UnsupportedMediaTypeError(AppError):
    status_code, code, message = 415, "unsupported_media_type", "The uploaded file type is not supported."


class UnprocessableError(AppError):
    status_code, code, message = 422, "unprocessable", "The request is well-formed but semantically invalid."


class RateLimitedError(AppError):
    status_code, code, message = 429, "rate_limited", "Too many requests. Retry after the indicated delay."

    def __init__(self, retry_after: int) -> None:
        super().__init__(headers={"Retry-After": str(max(1, retry_after))}, details={"retry_after_seconds": retry_after})


class ServiceUnavailableError(AppError):
    status_code, code, message = 503, "service_unavailable", "A required service is temporarily unavailable."


class ModelUnavailableError(ServiceUnavailableError):
    code, message = "model_unavailable", "The selected model is unavailable. Contact an administrator."


class RequestTooLarge(HTTPException):
    """Raised from the ASGI receive wrapper while a body is streamed (re-raised untouched by FastAPI)."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=PayloadTooLargeError.message)


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details, "request_id": current_request_id()}}


def _response(status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, details), headers=headers)


_HTTP_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    406: "not_acceptable",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "unprocessable",
    429: "rate_limited",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.warning("service error", extra={"error_code": exc.code})
        return _response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Workflow Manual 7.3: malformed requests / invalid request schema -> 400 with field-level messages.
        # Input values are not echoed back (they may contain sensitive data).
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()[:50]
        ]
        return _response(400, "validation_error", "The request failed validation.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "The request could not be processed."
        return _response(exc.status_code, code, message, headers=getattr(exc, "headers", None))

    @app.exception_handler(ArtifactError)
    async def _artifact_error(_request: Request, exc: ArtifactError) -> JSONResponse:
        logger.error("model artifact unavailable", extra={"error_code": exc.code})
        return _response(503, "model_unavailable", ModelUnavailableError.message, {"reason": exc.code})

    @app.exception_handler(MLError)
    async def _ml_error(_request: Request, exc: MLError) -> JSONResponse:
        status = 422
        if isinstance(exc, InferenceError) and exc.code == "inference_failed" and not exc.details:
            status = 500
        return _response(status, exc.code, exc.message, exc.details or None)

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception", exc_info=exc)
        return _response(500, "internal_error", "An unexpected error occurred. Quote the request ID when reporting it.")
