"""UC1 quick analysis: strict feature validation (Security Req. 5.3), bounded, not persisted, audited."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.models import ModelVersion
from tests.conftest import Actor
from tests.fixtures.data import unsw_frame


def record(seed: int = 1) -> dict[str, Any]:
    row = unsw_frame(1, seed=seed, with_labels=False).iloc[0].to_dict()
    row.pop("id")
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}


def analyze(client: TestClient, actor: Actor, model: ModelVersion, features: dict[str, Any], mode: str = "combined"):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/analyze/record",
        headers=actor.headers,
        json={"model_version_id": str(model.id), "mode": mode, "features": features},
    )


def test_single_record(client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]) -> None:
    response = analyze(client, actors["analyst"], models["unsw"], record())
    assert response.status_code == 200, response.text
    body = response.json()
    result = body["results"][0]
    assert body["persisted"] is False and body["risk_policy_version"] == "1.0.0"
    assert 0 <= result["risk_score"] <= 100 and result["risk_band"] in {"low", "medium", "high", "critical"}
    assert result["probability"] is None and result["scores_calibrated"] is False
    assert result["explanation"]["disclaimer"]
    audit = client.get("/api/v1/audit-logs", headers=actors["admin"].headers, params={"action": "analysis.quick"}).json()
    assert audit["total"] == 1 and "features" not in str(audit["items"][0]["details"])


def test_raw_feature_spellings_and_missing_values(
    client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]
) -> None:
    features = record()
    features["Dur"] = features.pop("dur")  # raw/case variants are normalized
    features["sbytes"] = None  # unknown value -> imputed by the trained preprocessor
    assert analyze(client, actors["analyst"], models["unsw"], features).status_code == 200


def test_invalid_records_rejected(client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion]) -> None:
    analyst, model = actors["analyst"], models["unsw"]
    unknown = analyze(client, analyst, model, {**record(), "evil_column": 1})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "feature_schema_mismatch"
    missing = record()
    missing.pop("rate")
    assert analyze(client, analyst, model, missing).status_code == 422
    assert analyze(client, analyst, model, {**record(), "dur": True}).status_code == 400  # wrong JSON type: schema error
    for bad in ("12", 1e300):  # right shape, semantically invalid
        response = analyze(client, analyst, model, {**record(), "dur": bad})
        assert response.status_code == 422, bad
    non_finite = client.post(
        "/api/v1/analyze/record",
        headers={**analyst.headers, "Content-Type": "application/json"},
        content=b'{"model_version_id": "%s", "features": {"dur": NaN}}' % str(model.id).encode(),
    )
    assert non_finite.status_code in (400, 422)


def test_batch_limits_and_roles(client: TestClient, actors: dict[str, Actor], models: dict[str, ModelVersion], settings) -> None:  # type: ignore[no-untyped-def]
    batch = {"model_version_id": str(models["unsw"].id), "records": [{"features": record(s)} for s in range(5)]}
    ok = client.post("/api/v1/analyze/batch", headers=actors["analyst"].headers, json=batch)
    assert ok.status_code == 200 and [r["index"] for r in ok.json()["results"]] == [0, 1, 2, 3, 4]
    too_many = {**batch, "records": [{"features": record()}] * (settings.quick_analysis_max_records + 1)}
    assert client.post("/api/v1/analyze/batch", headers=actors["analyst"].headers, json=too_many).status_code == 422
    assert client.post("/api/v1/analyze/batch", headers=actors["viewer"].headers, json=batch).status_code == 403
    anomaly_only = analyze(client, actors["analyst"], models["unsw"], record(), mode="anomaly").json()["results"][0]
    assert anomaly_only["predicted_label"] == "unclassified" and anomaly_only["classifier_score"] is None
