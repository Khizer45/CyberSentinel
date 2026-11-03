"""Shared schema building blocks: base models, pagination envelope, error envelope, validators."""

import re
from typing import Annotated, Any, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

T = TypeVar("T")

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[A-Za-z0-9-]{2,63}$")


def _validate_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL.match(value):
        raise ValueError("must be a valid e-mail address")
    return value


Email = Annotated[str, AfterValidator(_validate_email)]


class ApiModel(BaseModel):
    """Base for response models built from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


class RequestModel(BaseModel):
    """Base for request bodies: unknown fields are rejected (prevents mass assignment)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class MessageResponse(BaseModel):
    message: str


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Malformed request or invalid request schema"},
    401: {"model": ErrorResponse, "description": "Missing or invalid authentication"},
    403: {"model": ErrorResponse, "description": "Authenticated but not permitted"},
    404: {"model": ErrorResponse, "description": "Resource not found (or not accessible)"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
}
