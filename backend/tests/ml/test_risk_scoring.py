"""ML-07: risk scores are versioned policy outputs with documented, testable formulas."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.ml.risk import AnomalyReference, anomaly_component, compute_risk, load_policy
from app.ml.risk.policy import RiskPolicy

POLICY = load_policy(Path(__file__).resolve().parents[2] / "config" / "risk_policy.json")
REF = AnomalyReference(0.45, 0.62, 0.80)
CLASSES = ["Benign", "DoS", "PortScan"]


def test_documented_worked_example() -> None:
    result = compute_risk(
        POLICY,
        size=1,
        class_probabilities=np.array([[0.02, 0.95, 0.03]]),
        classes=CLASSES,
        benign_class="Benign",
        anomaly_scores=np.array([0.70]),
        anomaly_reference=REF,
        is_anomaly=np.array([True]),
        needs_review=np.array([False]),
    )
    assert result.score[0] == pytest.approx(89.43, abs=0.01)
    assert result.band[0] == "critical" and bool(result.is_alert[0])


def test_anomaly_component_anchors() -> None:
    values = anomaly_component(np.array([0.1, 0.45, 0.62, 0.80, 2.0]), REF)
    assert values.tolist() == pytest.approx([0.0, 0.0, 0.5, 1.0, 1.0])


@pytest.mark.parametrize(
    ("score", "band"),
    [(0.0, "low"), (24.99, "low"), (25.0, "medium"), (49.99, "medium"), (50.0, "high"), (75.0, "critical"), (100.0, "critical")],
)
def test_band_boundaries(score: float, band: str) -> None:
    assert POLICY.band_for(score) == band


def test_floors_apply_and_scores_stay_in_range() -> None:
    proba = np.array([[0.99, 0.005, 0.005], [0.99, 0.005, 0.005]])
    result = compute_risk(
        POLICY,
        size=2,
        class_probabilities=proba,
        classes=CLASSES,
        benign_class="Benign",
        anomaly_scores=np.array([0.3, 0.3]),
        anomaly_reference=REF,
        is_anomaly=np.array([True, False]),
        needs_review=np.array([False, True]),
    )
    assert result.score.tolist() == [25.0, 25.0]
    assert list(result.floor_applied) == ["anomaly", "needs_review"]
    assert np.all((result.score >= 0) & (result.score <= 100))


def test_classifier_only_and_anomaly_only() -> None:
    clf_only = compute_risk(
        POLICY, size=1, class_probabilities=np.array([[0.0, 0.0, 1.0]]), classes=CLASSES, benign_class="Benign"
    )
    assert clf_only.score[0] == pytest.approx(60.0)  # PortScan weight 0.6
    anomaly_only = compute_risk(
        POLICY, size=1, anomaly_scores=np.array([0.62]), anomaly_reference=REF, is_anomaly=np.array([True])
    )
    assert anomaly_only.score[0] == pytest.approx(50.0)
    with pytest.raises(ValueError):
        compute_risk(POLICY, size=1)


def test_invalid_policies_rejected() -> None:
    data = POLICY.model_dump(mode="json")
    data["weights"] = {"classifier": 0.9, "anomaly": 0.3}
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(data)
    data = POLICY.model_dump(mode="json")
    data["bands"][2]["min_score"] = 10
    with pytest.raises(ValidationError):
        RiskPolicy.model_validate(data)
