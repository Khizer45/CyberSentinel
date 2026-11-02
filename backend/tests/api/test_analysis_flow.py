"""End-to-end analysis lifecycle (FR-07..FR-16, NFR-04): upload → job → predictions → alerts → review → export."""

from __future__ import annotations

import csv
import io
import uuid

from fastapi.testclient import TestClient

from app.db.session import Database
from app.models import AnalysisJob, ModelVersion, Prediction
from tests.conftest import Actor, upload
from tests.fixtures.data import cic_traffic_labelling_csv, unsw_csv


def run_job(client: TestClient, actor: Actor, dataset_id: str, model: ModelVersion, mode: str = "combined"):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/analyses",
        headers=actor.headers,
        json={"dataset_id": dataset_id, "model_version_id": str(model.id), "requested_mode": mode},
    )


def test_full_lifecycle(
    client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion], database: Database
) -> None:
    analyst = actors["analyst"]
    dataset = upload(client, analyst, unsw_csv(rows=400, seed=21)).json()
    response = run_job(client, analyst, dataset["id"], models["unsw"])
    assert response.status_code == 202, response.text
    assert response.headers["location"] == f"/api/v1/analyses/{response.json()['id']}"
    job = client.get(f"/api/v1/analyses/{response.json()['id']}", headers=analyst.headers).json()
    assert job["status"] == "completed" and job["processed_rows"] == 400 and job["progress"] == 1.0
    summary = job["summary"]
    assert summary["rows"]["processed"] == 400 and summary["risk_policy_version"] == "1.0.0"
    assert sum(summary["risk_band_counts"].values()) == 400
    evaluation = summary["evaluation"]
    assert evaluation["labeled_rows"] == 400 and evaluation["classification"]["confusion_matrix"]["labels"]
    assert summary["model"]["manifest_sha256"] == models["unsw"].artifact_sha256

    page = client.get(
        f"/api/v1/analyses/{job['id']}/predictions", headers=analyst.headers, params={"limit": 50, "sort": "-risk_score"}
    ).json()
    assert page["total"] == 400 and len(page["items"]) == 50
    scores = [p["risk_score"] for p in page["items"]]
    assert scores == sorted(scores, reverse=True)
    first = page["items"][0]
    assert first["probability"] is None and 0 <= first["classifier_score"] <= 1  # uncalibrated model
    filtered = client.get(
        f"/api/v1/analyses/{job['id']}/predictions",
        headers=analyst.headers,
        params={"risk_band": ["high", "critical"], "limit": 100},
    ).json()
    assert all(p["risk_band"] in {"high", "critical"} for p in filtered["items"])

    alerts = client.get("/api/v1/alerts", headers=analyst.headers, params={"analysis_job_id": job["id"], "limit": 100}).json()
    assert alerts["total"] == summary["alert_count"] > 0
    alert = alerts["items"][0]
    assert alert["status"] == "open" and alert["review_count"] == 0
    detail = client.get(f"/api/v1/alerts/{alert['id']}", headers=analyst.headers).json()
    assert detail["model_version"]["model_name"] == models["unsw"].model_name and detail["dataset"]["id"] == dataset["id"]
    assert detail["explanation"]["disclaimer"] and detail["explanation"]["risk"]["policy_version"] == "1.0.0"
    assert detail["scores_calibrated"] is False

    review = client.post(
        f"/api/v1/predictions/{alert['id']}/reviews",
        headers=analyst.headers,
        json={"disposition": "needs_investigation", "notes": "Checking with the network team.\nTicket 42"},
    )
    assert review.status_code == 201 and review.json()["notes"].endswith("Ticket 42")
    assert client.get("/api/v1/alerts", headers=analyst.headers, params={"status": "investigating"}).json()["total"] == 1
    client.post(f"/api/v1/predictions/{alert['id']}/reviews", headers=analyst.headers, json={"disposition": "true_positive"})
    history = client.get(f"/api/v1/predictions/{alert['id']}/reviews", headers=analyst.headers).json()
    assert [r["disposition"] for r in history] == ["true_positive", "needs_investigation"]  # append-only, newest first
    assert client.get(f"/api/v1/alerts/{alert['id']}", headers=analyst.headers).json()["alert_status"] == "closed"
    invalid = client.post(f"/api/v1/predictions/{alert['id']}/reviews", headers=analyst.headers, json={"disposition": "ignore"})
    assert invalid.status_code == 400

    export = client.get(f"/api/v1/analyses/{job['id']}/export", headers=analyst.headers, params={"format": "csv"})
    assert export.status_code == 200 and export.headers["x-export-truncated"] == "false"
    rows = list(csv.DictReader(io.StringIO(export.text)))
    assert len(rows) == 400 and rows[0]["model_name"] == models["unsw"].model_name and rows[0]["risk_policy_version"] == "1.0.0"
    json_export = client.get(
        f"/api/v1/analyses/{job['id']}/export", headers=analyst.headers, params={"format": "json", "is_alert": True}
    )
    assert len(json_export.json()) == summary["alert_count"]

    metrics = client.get("/api/v1/metrics/summary", headers=actors["viewer"].headers).json()
    assert metrics["total_records"] == 400 and metrics["alert_count"] == summary["alert_count"]
    assert metrics["open_alert_count"] == summary["alert_count"] - 1
    assert metrics["malicious_count"] + metrics["benign_count"] + metrics["needs_review_count"] == 400
    trends = client.get("/api/v1/metrics/trends", headers=analyst.headers).json()
    assert sum(p["records"] for p in trends["points"]) == 400

    with database.session() as session:  # NFR-04 traceability: prediction → job → model/dataset/policy
        prediction = session.get(Prediction, uuid.UUID(alert["id"]))
        stored_job = session.get(AnalysisJob, prediction.analysis_job_id)
        assert stored_job.model_version.artifact_sha256 == models["unsw"].artifact_sha256
        assert stored_job.dataset.sha256 == dataset["sha256"] and stored_job.risk_policy_version == "1.0.0"


def test_other_analyst_cannot_see_job_or_alerts(
    client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]
) -> None:
    dataset = upload(client, actors["analyst"], unsw_csv(rows=60, seed=5)).json()
    job = run_job(client, actors["analyst"], dataset["id"], models["unsw"]).json()
    other = actors["analyst2"].headers
    assert client.get(f"/api/v1/analyses/{job['id']}", headers=other).status_code == 404
    assert client.get(f"/api/v1/analyses/{job['id']}/predictions", headers=other).status_code == 404
    assert client.get("/api/v1/alerts", headers=other).json()["total"] == 0
    any_prediction = client.get(f"/api/v1/analyses/{job['id']}/predictions", headers=actors["analyst"].headers).json()["items"][0]
    assert client.get(f"/api/v1/predictions/{any_prediction['id']}", headers=other).status_code == 404
    assert (
        client.post(
            f"/api/v1/predictions/{any_prediction['id']}/reviews", headers=other, json={"disposition": "benign"}
        ).status_code
        == 404
    )
    assert client.get("/api/v1/alerts", headers=actors["admin"].headers).json()["total"] >= 0


def test_ip_context_is_pseudonymized_and_filterable(
    client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]
) -> None:
    analyst = actors["analyst"]
    dataset = upload(client, analyst, cic_traffic_labelling_csv(rows=120, seed=8)).json()
    job = run_job(client, analyst, dataset["id"], models["cic"]).json()
    assert job["status"] == "completed", job
    first = client.get(f"/api/v1/analyses/{job['id']}/predictions", headers=analyst.headers).json()["items"][0]
    detail = client.get(f"/api/v1/predictions/{first['id']}", headers=analyst.headers).json()
    context = detail["flow_context"]
    assert context["src_ip"].startswith("ip_") and context["dst_ip"].startswith("ip_")
    assert "192.168" not in str(context) and "10.0.0" not in str(context)
    assert context["dst_port"] >= 0 and context["protocol"] == "6"
    # Filtering by an address that never occurs matches nothing; raw IPs are never stored, so a match requires the key.
    none = client.get(
        "/api/v1/alerts", headers=analyst.headers, params={"analysis_job_id": job["id"], "ip": "203.0.113.9"}
    ).json()
    assert none["total"] == 0


def test_job_preconditions(client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]) -> None:
    analyst = actors["analyst"]
    unsw = upload(client, analyst, unsw_csv(rows=30, seed=6)).json()
    incompatible = run_job(client, analyst, unsw["id"], models["cic"])
    assert incompatible.status_code == 422 and incompatible.json()["error"]["code"] == "incompatible_dataset"
    unsupported = run_job(client, analyst, unsw["id"], models["unsw_binary"], mode="anomaly")
    assert unsupported.status_code == 422 and unsupported.json()["error"]["code"] == "unsupported_mode"
    assert run_job(client, actors["analyst2"], unsw["id"], models["unsw"]).status_code == 404
    finished = run_job(client, analyst, unsw["id"], models["unsw_binary"], mode="classification").json()
    assert finished["status"] == "completed"
    assert client.post(f"/api/v1/analyses/{finished['id']}/cancel", headers=analyst.headers).status_code == 409
    in_use_free = client.delete(f"/api/v1/datasets/{unsw['id']}", headers=analyst.headers)
    assert in_use_free.status_code == 204  # completed jobs keep their results; the dataset metadata stays traceable


def test_unapproved_or_missing_artifacts_block_jobs(
    client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion], database: Database
) -> None:
    analyst = actors["analyst"]
    dataset = upload(client, analyst, unsw_csv(rows=30, seed=7)).json()
    retired = client.patch(
        f"/api/v1/models/{models['unsw'].id}/status", headers=actors["admin"].headers, json={"status": "retired"}
    )
    assert retired.status_code == 200
    blocked = run_job(client, analyst, dataset["id"], models["unsw"])
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "model_not_approved"
