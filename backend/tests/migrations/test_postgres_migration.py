"""Alembic migration tests against a real PostgreSQL database.

Skipped unless ``TEST_POSTGRES_MIGRATION_URL`` points to an **empty, disposable** PostgreSQL database,
for example::

    TEST_POSTGRES_MIGRATION_URL=postgresql+psycopg://postgres@localhost:5432/cs_migration_test pytest tests/migrations

The test upgrades to head, compares the migrated schema with the ORM metadata, probes constraints and
append-only triggers, then downgrades to base. Never point it at a database holding real data.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from app.db.base import Base
import app.models  # noqa: F401

MIGRATION_URL = os.environ.get("TEST_POSTGRES_MIGRATION_URL")
pytestmark = pytest.mark.skipif(not MIGRATION_URL, reason="TEST_POSTGRES_MIGRATION_URL not set")

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def alembic_config(monkeypatch_module: pytest.MonkeyPatch) -> Config:
    monkeypatch_module.setenv("DATABASE_URL", MIGRATION_URL or "")
    return Config(str(BACKEND_DIR / "alembic.ini"))


@pytest.fixture(scope="module")
def monkeypatch_module() -> Iterator[pytest.MonkeyPatch]:
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def migrated_engine(alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_engine(MIGRATION_URL or "")
    yield engine
    engine.dispose()
    command.downgrade(alembic_config, "base")


def test_migration_matches_orm_metadata(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []


def test_all_tables_and_triggers_exist(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        triggers = set(conn.execute(text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())
    assert {"users", "datasets", "model_versions", "analysis_jobs", "predictions", "alert_reviews", "audit_logs"} <= tables
    assert {"audit_logs_append_only", "audit_logs_no_truncate", "alert_reviews_append_only"} <= triggers


def _insert_user(conn, email: str = "owner@example.org") -> uuid.UUID:  # type: ignore[no-untyped-def]
    user_id = uuid.uuid4()
    conn.execute(
        text("INSERT INTO users (id, email, password_hash, display_name, role) VALUES (:i, :e, 'x', 'Owner', 'admin')"),
        {"i": user_id, "e": email},
    )
    return user_id


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_logs SET action = 'tampered'",
        "DELETE FROM audit_logs",
        "TRUNCATE audit_logs",
    ],
)
def test_audit_log_is_append_only(migrated_engine: Engine, statement: str) -> None:
    with migrated_engine.begin() as conn:
        user_id = _insert_user(conn, f"{uuid.uuid4().hex[:8]}@example.org")
        conn.execute(text("INSERT INTO audit_logs (actor_user_id, action) VALUES (:u, 'auth.login.success')"), {"u": user_id})
    with pytest.raises(DBAPIError), migrated_engine.begin() as conn:
        conn.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO users (email, password_hash, display_name, role) VALUES ('x@example.org', 'h', 'X', 'root')",
        "INSERT INTO users (email, password_hash, display_name, role) VALUES ('Upper@example.org', 'h', 'X', 'viewer')",
        "INSERT INTO datasets (name, source_type, status) VALUES ('d', 'upload', 'pending')",
        "INSERT INTO datasets (name, source_type, status) VALUES ('d', 'import', 'unknown')",
        "INSERT INTO model_versions (model_name, version, model_type, dataset_family, artifact_uri, artifact_sha256,"
        " preprocessing_version, feature_schema_version) VALUES ('m', '1', 'classifier', 'cicids2017', 'b', 'not-a-hash',"
        " 'p', 'f')",
    ],
)
def test_check_constraints_reject_invalid_rows(migrated_engine: Engine, statement: str) -> None:
    with pytest.raises(DBAPIError), migrated_engine.begin() as conn:
        conn.execute(text(statement))


def test_duplicate_email_and_model_version_rejected(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        _insert_user(conn, "dup@example.org")
    with pytest.raises(DBAPIError), migrated_engine.begin() as conn:
        _insert_user(conn, "dup@example.org")

    insert_model = text(
        "INSERT INTO model_versions (model_name, version, model_type, dataset_family, artifact_uri, artifact_sha256,"
        " preprocessing_version, feature_schema_version) VALUES ('dup-model', '1.0.0', 'classifier', 'cicids2017',"
        " 'bundles/dup-model/1.0.0', :h, 'p', 'f')"
    )
    with migrated_engine.begin() as conn:
        conn.execute(insert_model, {"h": "a" * 64})
    with pytest.raises(DBAPIError), migrated_engine.begin() as conn:
        conn.execute(insert_model, {"h": "b" * 64})
