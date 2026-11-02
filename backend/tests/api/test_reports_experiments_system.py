"""Reports (US4), experiments (Model Lab, read-only), system info, risk policy and health states."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.ml.artifacts.compatibility import current_runtime
from app.ml.evaluation.experiment_record import ExperimentRecord, write_experiment
from app.models import ModelVersion
from tests.conftest import Actor


def test_summary_report_json_and_csv(client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]) -> None:
    viewer = actors["viewer"].headers
    report = client.get("/api/v1/reports/summary", headers=viewer)
    assert report.status_code == 200 and report.json()["generated_by"] == "viewer@example.org"
    assert len(report.json()["models"]) == 3
    csv_report = client.get("/api/v1/reports/summary", headers=viewer, params={"format": "csv"})
    assert csv_report.headers["content-type"].startswith("text/csv") and csv_report.text.startswith("section,key,value")


def test_experiments_are_served_read_only_and_invalid_files_skipped(
    client: TestClient, actors: dict[str, Actor], settings
) -> None:  # type: ignore[no-untyped-def]
    record = ExperimentRecord(
        experiment_id="unsw_nb15-semi-supervised-label-budget",
        experiment_type="semi_supervised_label_budget",
        title="Label budget",
        dataset_family="unsw_nb15",
        schema_version="unsw-nb15-flow-v1",
        created_at=datetime.now(UTC),
        columns={"macro_f1": "macro F1"},
        rows=[{"method": "label_spreading", "label_budget": 0.1, "seed": 0, "macro_f1": 0.5}],
        runtime=current_runtime(),
    )
    settings.experiments_dir.mkdir(parents=True, exist_ok=True)
    write_experiment(record, settings.experiments_dir)
    (settings.experiments_dir / "broken.json").write_text("{not json")
    listing = client.get("/api/v1/experiments", headers=actors["viewer"].headers).json()
    assert [e["experiment_id"] for e in listing] == [record.experiment_id]
    detail = client.get(f"/api/v1/experiments/{record.experiment_id}", headers=actors["viewer"].headers).json()
    assert detail["rows"][0]["macro_f1"] == 0.5
    assert client.get("/api/v1/experiments/..%2Fsecret", headers=actors["viewer"].headers).status_code == 404
    for path in settings.experiments_dir.glob("*.json"):
        path.unlink()


def test_risk_policy_and_system_info(client: TestClient, actors: dict[str, Actor]) -> None:
    policy = client.get("/api/v1/risk-policy", headers=actors["viewer"].headers).json()
    assert policy["policy"]["policy_version"] == "1.0.0" and len(policy["sha256"]) == 64
    info = client.get("/api/v1/system/info", headers=actors["viewer"].headers).json()
    assert info["limits"]["max_upload_mb"] == 5 and "unsw-nb15-flow-v1" in info["supported_schemas"]
    assert "secret" not in json.dumps(info).lower() and "database" not in json.dumps(info).lower()


def test_health_reports_registry_state(client: TestClient, models: dict[str, ModelVersion]) -> None:
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["checks"]["model_registry"] == "ok"
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
