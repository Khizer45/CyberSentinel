"""Typed application configuration loaded from environment variables.

Variable names follow the configuration contract of the Developer Manual (5.4): ``APP_ENV``,
``DATABASE_URL``, ``MODEL_DIR``, ``MODEL_MANIFEST``, ``MAX_UPLOAD_MB``, ``LOG_LEVEL``,
``CORS_ORIGINS`` and ``AUTH_SECRET``; the remaining variables are documented in
``docs/configuration_guide.md`` and ``backend/.env.example``.

Security properties:

* Secrets (``DATABASE_URL``, ``AUTH_SECRET``, ``IP_PSEUDONYMIZATION_KEY``) have **no defaults** and are
  held as :class:`~pydantic.SecretStr` so they never appear in ``repr`` or logs.
* Startup fails if ``AUTH_SECRET`` is shorter than 32 characters or if ``CORS_ORIGINS`` contains a wildcard.
* Relative paths are resolved against the ``backend/`` directory, not the current working directory.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]

_RATE_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour|day)\s*$")


def parse_rate(value: str) -> tuple[int, int]:
    """Parse ``"10/minute"`` into ``(limit, window_seconds)``."""
    match = _RATE_PATTERN.match(value)
    if not match:
        raise ValueError(f"invalid rate limit {value!r}; expected '<count>/<second|minute|hour|day>'")
    windows = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    count = int(match.group(1))
    if count <= 0:
        raise ValueError("rate limit count must be positive")
    return count, windows[match.group(2)]


class Settings(BaseSettings):
    """All runtime configuration. Instantiate through :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------------------------
    app_name: str = "CyberSentinel"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = True
    enable_api_docs: bool = True

    # --- Database ----------------------------------------------------------------------------
    database_url: SecretStr
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    db_pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    db_statement_timeout_ms: int = Field(default=60_000, ge=1_000, le=3_600_000)
    db_echo: bool = False

    # --- Authentication ----------------------------------------------------------------------
    auth_secret: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "cybersentinel"
    jwt_audience: str = "cybersentinel-api"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_ttl_hours: int = Field(default=12, ge=1, le=168)
    refresh_cookie_name: str = "cs_refresh"
    cookie_secure: bool = True
    cookie_samesite: Literal["strict", "lax"] = "strict"
    login_max_failed_attempts: int = Field(default=5, ge=1, le=50)
    login_lockout_minutes: int = Field(default=15, ge=1, le=1440)
    password_min_length: int = Field(default=12, ge=8, le=64)

    # --- HTTP --------------------------------------------------------------------------------
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:5173"])
    trust_proxy_headers: bool = False
    hsts_enabled: bool = False
    max_json_body_kb: int = Field(default=1024, ge=16, le=65_536)

    # --- Model artifacts (trusted, read-only for the API) -------------------------------------
    model_dir: Path = Path("../model_artifacts")
    model_manifest: Path | None = None
    experiments_dir: Path | None = None
    max_artifact_mb: int = Field(default=2048, ge=1, le=65_536)
    model_cache_size: int = Field(default=4, ge=1, le=64)
    model_preload: bool = False

    # --- Dataset uploads ---------------------------------------------------------------------
    upload_dir: Path = Path("storage/uploads")
    max_upload_mb: int = Field(default=200, ge=1, le=10_240)
    max_upload_rows: int = Field(default=1_000_000, ge=1, le=100_000_000)
    max_invalid_value_fraction: float = Field(default=0.2, ge=0.0, le=1.0)
    reject_unknown_columns: bool = False
    dataset_retention_days: int = Field(default=90, ge=1, le=3650)

    # --- Analysis jobs -----------------------------------------------------------------------
    job_workers: int = Field(default=2, ge=1, le=32)
    job_queue_max: int = Field(default=20, ge=1, le=1000)
    job_stale_after_seconds: int = Field(default=600, ge=30, le=86_400)
    inference_batch_size: int = Field(default=5000, ge=100, le=200_000)
    explain_scope: Literal["alerts", "alerts_and_review", "all", "none"] = "alerts_and_review"
    explain_max_rows_per_job: int = Field(default=2000, ge=0, le=1_000_000)
    explain_top_k: int = Field(default=8, ge=1, le=50)
    quick_analysis_max_records: int = Field(default=100, ge=1, le=10_000)
    export_max_rows: int = Field(default=100_000, ge=1, le=10_000_000)

    # --- Risk policy -------------------------------------------------------------------------
    risk_policy_path: Path = Path("config/risk_policy.json")

    # --- Rate limits ("<count>/<second|minute|hour|day>") -----------------------------------
    rate_limit_enabled: bool = True
    rate_limit_login: str = "10/minute"
    rate_limit_upload: str = "30/hour"
    rate_limit_analysis: str = "60/hour"
    rate_limit_quick_analysis: str = "120/minute"
    rate_limit_export: str = "30/hour"
    rate_limit_default: str = "600/minute"

    # --- Privacy -----------------------------------------------------------------------------
    ip_pseudonymization_key: SecretStr | None = None
    audit_client_ip: bool = True

    # -----------------------------------------------------------------------------------------
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcards(cls, value: list[str]) -> list[str]:
        for origin in value:
            if "*" in origin:
                raise ValueError("CORS_ORIGINS must be an explicit allowlist; wildcards are not permitted")
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"invalid CORS origin {origin!r}")
        return [origin.rstrip("/") for origin in value]

    @field_validator(
        "rate_limit_login",
        "rate_limit_upload",
        "rate_limit_analysis",
        "rate_limit_quick_analysis",
        "rate_limit_export",
        "rate_limit_default",
    )
    @classmethod
    def _valid_rate(cls, value: str) -> str:
        parse_rate(value)
        return value

    @field_validator("auth_secret")
    @classmethod
    def _strong_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("AUTH_SECRET must be at least 32 characters (generate one with `python -c \"import secrets; print(secrets.token_urlsafe(48))\"`)")
        if secret.lower().startswith(("change", "replace", "your-")):
            raise ValueError("AUTH_SECRET still contains the placeholder value from .env.example")
        return value

    @field_validator("database_url")
    @classmethod
    def _supported_database(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value()
        if not url.startswith(("postgresql+psycopg://", "postgresql://", "sqlite")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL (postgresql+psycopg://...) or sqlite for tests")
        return value

    @model_validator(mode="after")
    def _resolve_paths_and_production_rules(self) -> Settings:
        def resolve(path: Path) -> Path:
            return (path if path.is_absolute() else BACKEND_DIR / path).resolve()

        self.model_dir = resolve(self.model_dir)
        self.model_manifest = resolve(self.model_manifest) if self.model_manifest else self.model_dir / "registry.json"
        self.experiments_dir = (
            resolve(self.experiments_dir) if self.experiments_dir else self.model_dir / "experiments"
        )
        self.upload_dir = resolve(self.upload_dir)
        self.risk_policy_path = resolve(self.risk_policy_path)

        if self.app_env == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if self.database_url.get_secret_value().startswith("sqlite"):
                raise ValueError("SQLite is only supported for automated tests; use PostgreSQL in production")
            insecure = [origin for origin in self.cors_origins if origin.startswith("http://")]
            if insecure:
                raise ValueError(f"production CORS origins must use https: {insecure}")
        return self

    # Convenience accessors --------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_json_body_bytes(self) -> int:
        return self.max_json_body_kb * 1024

    @property
    def max_artifact_bytes(self) -> int:
        return self.max_artifact_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (cached). Tests clear the cache to override values."""
    return Settings()  # type: ignore[call-arg]  # required values come from the environment
