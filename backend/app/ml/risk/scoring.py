"""Pure, vectorized risk scoring (testable without a database or model).

Formula (policy-versioned, see docs/risk_scoring_policy.md)::

    C = Σ_{k ≠ benign} p_k · w(k)                      classifier component ∈ [0,1] (expected attack severity)
    A = piecewise-linear(anomaly_score; median→0, threshold→0.5, upper→1)   anomaly component ∈ [0,1]
    base = w_c·C + w_a·A   (if both components exist; otherwise the available one alone)
    risk = 100 · clip(base, 0, 1)
    risk = max(risk, floor_anomaly)       if is_anomaly
    risk = max(risk, floor_needs_review)  if needs_review
    band = highest band whose min_score ≤ round(risk, 2)
    alert = band ≥ alerting.min_band  OR (alert_on_anomaly ∧ is_anomaly) OR (alert_on_needs_review ∧ needs_review)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.ml.risk.policy import RiskPolicy


@dataclass(frozen=True)
class AnomalyReference:
    benign_median: float
    threshold: float
    upper: float


@dataclass
class RiskResult:
    score: NDArray[np.float64]
    band: NDArray[np.object_]
    is_alert: NDArray[np.bool_]
    classifier_component: NDArray[np.float64] | None
    anomaly_component: NDArray[np.float64] | None
    floor_applied: NDArray[np.object_]

    def breakdown(self, i: int, policy: RiskPolicy) -> dict[str, object]:
        """Per-row explanation of how the score was computed (stored with explanations)."""
        return {
            "policy_version": policy.policy_version,
            "classifier_component": None if self.classifier_component is None else round(float(self.classifier_component[i]), 6),
            "anomaly_component": None if self.anomaly_component is None else round(float(self.anomaly_component[i]), 6),
            "weights": {"classifier": policy.weights.classifier, "anomaly": policy.weights.anomaly},
            "floor_applied": self.floor_applied[i],
            "risk_score": float(self.score[i]),
            "risk_band": str(self.band[i]),
        }


def anomaly_component(scores: NDArray[np.float64], ref: AnomalyReference) -> NDArray[np.float64]:
    """Map raw anomaly scores to [0, 1]: benign median → 0, threshold → 0.5, upper anchor → 1 (linear between)."""
    scores = np.asarray(scores, dtype=np.float64)
    out = np.interp(scores, [ref.benign_median, ref.threshold, ref.upper], [0.0, 0.5, 1.0])
    return np.clip(out, 0.0, 1.0)


def classifier_component(
    class_probabilities: NDArray[np.float64], classes: Sequence[str], benign_class: str, policy: RiskPolicy
) -> NDArray[np.float64]:
    """Expected attack severity: Σ over attack classes of probability × category weight."""
    proba = np.asarray(class_probabilities, dtype=np.float64)
    weights = np.array(
        [0.0 if c == benign_class else policy.category_weights.weight_for(c) for c in classes], dtype=np.float64
    )
    return np.clip(proba @ weights, 0.0, 1.0)


def compute_risk(
    policy: RiskPolicy,
    *,
    size: int,
    class_probabilities: NDArray[np.float64] | None = None,
    classes: Sequence[str] | None = None,
    benign_class: str | None = None,
    anomaly_scores: NDArray[np.float64] | None = None,
    anomaly_reference: AnomalyReference | None = None,
    is_anomaly: NDArray[np.bool_] | None = None,
    needs_review: NDArray[np.bool_] | None = None,
) -> RiskResult:
    c_comp = None
    a_comp = None
    if class_probabilities is not None:
        if classes is None or benign_class is None:
            raise ValueError("classes and benign_class are required with class_probabilities")
        c_comp = classifier_component(class_probabilities, classes, benign_class, policy)
    if anomaly_scores is not None:
        if anomaly_reference is None:
            raise ValueError("anomaly_reference is required with anomaly_scores")
        a_comp = anomaly_component(anomaly_scores, anomaly_reference)

    if c_comp is not None and a_comp is not None:
        base = policy.weights.classifier * c_comp + policy.weights.anomaly * a_comp
    elif c_comp is not None:
        base = c_comp
    elif a_comp is not None:
        base = a_comp
    else:
        raise ValueError("at least one model component is required to compute risk")

    score = 100.0 * np.clip(base, 0.0, 1.0)
    floor_applied = np.full(size, None, dtype=object)
    if is_anomaly is not None:
        mask = np.asarray(is_anomaly, dtype=bool) & (score < policy.floors.anomaly)
        score = np.where(mask, policy.floors.anomaly, score)
        floor_applied[mask] = "anomaly"
    if needs_review is not None:
        mask = np.asarray(needs_review, dtype=bool) & (score < policy.floors.needs_review)
        score = np.where(mask, policy.floors.needs_review, score)
        floor_applied[mask] = "needs_review"
    score = np.clip(np.round(score, 2), 0.0, 100.0)

    mins = np.array([band.min_score for band in policy.bands])
    names = np.array([band.name.value for band in policy.bands], dtype=object)
    band = names[np.searchsorted(mins, score, side="right") - 1]

    alert = np.array([policy.is_alert_band(b) for b in band], dtype=bool) if size else np.zeros(0, dtype=bool)
    if policy.alerting.alert_on_anomaly and is_anomaly is not None:
        alert |= np.asarray(is_anomaly, dtype=bool)
    if policy.alerting.alert_on_needs_review and needs_review is not None:
        alert |= np.asarray(needs_review, dtype=bool)
    return RiskResult(
        score=score,
        band=band,
        is_alert=alert,
        classifier_component=c_comp,
        anomaly_component=a_comp,
        floor_applied=floor_applied,
    )
