"""Shared pytest fixtures.

* Settings are constructed explicitly with ``_env_file=None`` so a developer's ``backend/.env`` (which may point
  at a real database) is never read by the test-suite.
* Each test gets a fresh database: in-memory SQLite by default, or PostgreSQL when ``TEST_DATABASE_URL`` points to
  a **disposable** database (tables are dropped and recreated for every test).
* Model bundles are tiny test fixtures fitted on synthetic data (see ``tests/fixtures/bundles.py``).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import Settings
from app.core.constants import ModelStatus, UserRole
from app.core.security import create_token, hash_password
from app.db.base import Base
from app.db.session import Database, build_engine, init_database
from app.main import create_app
from app.models import ModelVersion, User
from app.services import model_registry_service
from app.services.model_registry_service import ModelRegistry
from tests.fixtures.bundles import BuiltBundle, build_bundle

TEST_SECRET = "test-auth-secret-0123456789-abcdefghijklmnop"
PASSWORD = "Correct-Horse-9-Battery"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def bundle_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-wide MODEL_DIR with three fixture bundles (read-only for tests)."""
    root = tmp_path_factory.mktemp("model_artifacts")
    build_bundle(root, family="unsw_nb15", algorithm="random_forest")
    build_bundle(root, family="cicids2017", algorithm="xgboost")
    build_bundle(root, family="unsw_nb15", algorithm="random_forest", task="binary", with_anomaly=False)
    return root


@pytest.fixture(scope="session")
def bundles(bundle_dir: Path) -> dict[str, str]:
    """Model names of the session bundles keyed by a short alias."""
    return {
        "unsw": "unsw-nb15-random-forest-multiclass-test",
        "cic": "cicids2017-xgboost-multiclass-test",
        "unsw_binary": "unsw-nb15-random-forest-binary-test",
    }


def make_settings(tmp_path: Path, model_dir: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": TEST_DATABASE_URL or "sqlite://",
        "auth_secret": TEST_SECRET,
        "app_env": "test",
        "job_execution": "inline",
        "model_dir": model_dir,
        "upload_dir": tmp_path / "uploads",
        "risk_policy_path": BACKEND_DIR / "config" / "risk_policy.json",
        "rate_limit_enabled": False,
        "cookie_secure": False,
        "cors_origins": ["http://localhost:5173"],
        "ip_pseudonymization_key": "test-ip-pseudonymization-key",
        "log_json": False,
        "log_level": "WARNING",
        "max_upload_mb": 5,
        "explain_scope": "alerts_and_review",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine | None]:
    if not TEST_DATABASE_URL:
        yield None
        return
    engine = build_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def database(pg_engine: Engine | None) -> Iterator[Database]:
    engine = pg_engine or build_engine("sqlite://")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Database(engine)
    init_database(db)
    yield db
    if pg_engine is None:
        engine.dispose()


@pytest.fixture
def settings(tmp_path: Path, bundle_dir: Path) -> Settings:
    return make_settings(tmp_path, bundle_dir)


@pytest.fixture
def app(settings: Settings, database: Database) -> Any:
    return create_app(settings, database=database)


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@dataclass
class Actor:
    user: User
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def create_user(database: Database, settings: Settings, email: str, role: UserRole, *, password: str = PASSWORD) -> Actor:
    with database.session() as session:
        user = User(email=email, display_name=email.split("@")[0], role=role.value, password_hash=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)
    token, _ = create_token(settings, user_id=user.id, token_type="access", token_version=user.token_version, role=user.role)
    return Actor(user=user, token=token)


@pytest.fixture
def actors(database: Database, settings: Settings, client: TestClient) -> dict[str, Actor]:
    return {
        "admin": create_user(database, settings, "admin@example.org", UserRole.ADMIN),
        "analyst": create_user(database, settings, "analyst@example.org", UserRole.ANALYST),
        "analyst2": create_user(database, settings, "analyst2@example.org", UserRole.ANALYST),
        "viewer": create_user(database, settings, "viewer@example.org", UserRole.VIEWER),
    }


def register_models(database: Database, settings: Settings, *, approve: bool = True) -> dict[str, ModelVersion]:
    registry = ModelRegistry(settings)
    with database.session() as session:
        results = model_registry_service.sync_from_registry(session, settings, registry)
        assert all(r.outcome in {"registered", "unchanged"} for r in results), results
        models = {}
        for result in results:
            model = session.query(ModelVersion).filter_by(model_name=result.model_name, version=result.version).one()
            if approve and model.status != ModelStatus.APPROVED:
                model = model_registry_service.change_status(
                    session,
                    registry,
                    actor=None,
                    model_version_id=model.id,
                    new_status=ModelStatus.APPROVED,
                    reason="tests",
                    ip=None,
                )
            models[model.model_name] = model
        return models


@pytest.fixture
def models(database: Database, settings: Settings, client: TestClient, bundles: dict[str, str]) -> dict[str, ModelVersion]:
    registered = register_models(database, settings)
    return {alias: registered[name] for alias, name in bundles.items()}


@pytest.fixture
def private_model_dir(tmp_path: Path, bundle_dir: Path) -> Path:
    """A writable copy of the session bundles for tests that tamper with artifacts."""
    target = tmp_path / "private_models"
    shutil.copytree(bundle_dir, target)
    return target


def upload(
    client: TestClient,
    actor: Actor,
    content: bytes,
    *,
    filename: str = "flows.csv",
    name: str | None = None,
    schema_version: str | None = None,
    content_type: str = "text/csv",
) -> Any:
    data = {}
    if name is not None:
        data["name"] = name
    if schema_version is not None:
        data["schema_version"] = schema_version
    return client.post("/api/v1/datasets", headers=actor.headers, files={"file": (filename, content, content_type)}, data=data)


def build_extra_bundle(model_dir: Path, **kwargs: Any) -> BuiltBundle:
    return build_bundle(model_dir, **kwargs)
