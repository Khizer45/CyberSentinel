"""FR-06 / SEC-06: model metadata without artifact paths; governed status changes; verification."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.session import Database
from app.models import ModelVersion
from tests.conftest import Actor, make_settings, register_models


def test_metadata_never_exposes_artifact_location(
    client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]
) -> None:
    listing = client.get("/api/v1/models", headers=actors["viewer"].headers)
    assert listing.status_code == 200 and len(listing.json()) == 3
    text = json.dumps(listing.json())
    assert "artifact_uri" not in text and "bundles/" not in text and str(Path.home()) not in text
    item = next(m for m in listing.json() if m["model_name"] == models["unsw"].model_name)
    assert item["supported_modes"] == ["classification", "anomaly", "combined"] and item["probability_calibrated"] is False
    assert item["threshold_config"]["anomaly_detector"]["score_direction"] == "higher_is_more_anomalous"


def test_non_admins_only_see_approved(client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]) -> None:
    admin = actors["admin"].headers
    assert client.patch(f"/api/v1/models/{models['cic'].id}/status", headers=admin, json={"status": "retired"}).status_code == 200
    viewer_list = client.get("/api/v1/models", headers=actors["viewer"].headers).json()
    assert models["cic"].model_name not in {m["model_name"] for m in viewer_list}
    assert client.get(f"/api/v1/models/{models['cic'].id}", headers=actors["viewer"].headers).status_code == 404
    admin_list = client.get("/api/v1/models", headers=admin, params={"status": "retired"}).json()
    assert [m["model_name"] for m in admin_list] == [models["cic"].model_name]


def test_status_transitions(client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]) -> None:
    admin = actors["admin"].headers
    url = f"/api/v1/models/{models['unsw'].id}/status"
    revoked = client.patch(url, headers=admin, json={"status": "revoked", "reason": "suspected tampering"})
    assert revoked.status_code == 200 and revoked.json()["status_reason"] == "suspected tampering"
    again = client.patch(url, headers=admin, json={"status": "approved"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_status_transition"
    assert client.post(f"/api/v1/models/{models['unsw'].id}/verify", headers=admin).json()["verified"] is False


def test_approval_requires_successful_verification(tmp_path: Path, private_model_dir: Path, database: Database) -> None:
    settings = make_settings(tmp_path, private_model_dir)
    registered = register_models(database, settings, approve=False)
    model = registered["unsw-nb15-random-forest-multiclass-test"]
    (private_model_dir / model.artifact_uri / "preprocessor.joblib").write_bytes(b"tampered")
    from app.core.constants import ModelStatus
    from app.core.errors import UnprocessableError
    from app.services import model_registry_service
    from app.services.model_registry_service import ModelRegistry

    with database.session() as session:
        try:
            model_registry_service.change_status(
                session,
                ModelRegistry(settings),
                actor=None,
                model_version_id=model.id,
                new_status=ModelStatus.APPROVED,
                reason=None,
                ip=None,
            )
            raise AssertionError("approval should have failed")
        except UnprocessableError as exc:
            assert exc.code == "model_verification_failed"


def test_verify_detects_tampering_and_jobs_fail_closed(
    client: TestClient, actors: dict[str, Actor], tmp_path: Path, private_model_dir: Path, database: Database, app
) -> None:  # type: ignore[no-untyped-def]
    settings: Settings = make_settings(tmp_path, private_model_dir)
    app.state.settings = settings
    app.state.registry.settings = settings
    registered = register_models(database, settings)
    model = registered["unsw-nb15-random-forest-multiclass-test"]
    good = client.post(f"/api/v1/models/{model.id}/verify", headers=actors["admin"].headers).json()
    assert good["verified"] and {c["name"] for c in good["checks"]} >= {"load_and_integrity", "golden_parity"}
    (private_model_dir / model.artifact_uri / "classifier.joblib").write_bytes(b"tampered")
    bad = client.post(f"/api/v1/models/{model.id}/verify", headers=actors["admin"].headers).json()
    assert bad["verified"] is False
    audit = client.get("/api/v1/audit-logs", headers=actors["admin"].headers, params={"action": "model.integrity.failure"}).json()
    assert audit["total"] >= 1
