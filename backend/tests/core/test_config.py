"""Configuration safety rules (SEC-05, SEC-10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, parse_rate
from tests.conftest import TEST_SECRET


def build(**kwargs):  # type: ignore[no-untyped-def]
    base = {"database_url": "sqlite://", "auth_secret": TEST_SECRET, "app_env": "test"}
    base.update(kwargs)
    return Settings(_env_file=None, **base)


def test_short_or_placeholder_secret_rejected() -> None:
    with pytest.raises(ValidationError):
        build(auth_secret="too-short")
    with pytest.raises(ValidationError):
        build(auth_secret="replace-with-a-long-random-secret-0123456789")


def test_cors_wildcard_rejected_and_csv_parsed() -> None:
    with pytest.raises(ValidationError):
        build(cors_origins="*")
    assert build(cors_origins="http://a.example, https://b.example/").cors_origins == ["http://a.example", "https://b.example"]


def test_production_requires_secure_cookies_https_origins_and_postgres() -> None:
    with pytest.raises(ValidationError):
        build(app_env="production", cookie_secure=False)
    with pytest.raises(ValidationError):
        build(app_env="production", database_url="postgresql+psycopg://u:p@db/x", cors_origins="http://insecure.example")
    with pytest.raises(ValidationError):
        build(app_env="production")  # sqlite
    ok = build(app_env="production", database_url="postgresql+psycopg://u:p@db/x", cors_origins="https://app.example")
    assert ok.is_production


def test_inline_jobs_only_in_test_env() -> None:
    with pytest.raises(ValidationError):
        build(app_env="development", job_execution="inline")


def test_relative_paths_resolve_against_backend_dir() -> None:
    settings = build()
    assert settings.model_dir.is_absolute() and settings.model_dir.name == "model_artifacts"
    assert settings.model_manifest == settings.model_dir / "registry.json"


def test_rate_parsing() -> None:
    assert parse_rate("10/minute") == (10, 60)
    with pytest.raises(ValueError):
        parse_rate("ten per minute")
