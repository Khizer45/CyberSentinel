"""Applies the versioned risk policy to inference outputs (ML-07)."""

from __future__ import annotations

from pathlib import Path

from app.ml.artifacts.bundle import LoadedBundle
from app.ml.artifacts.integrity import sha256_file
from app.ml.inference import InferenceOutput
from app.ml.risk import AnomalyReference, RiskPolicy, RiskResult, compute_risk, load_policy


class RiskScoringService:
    def __init__(self, policy_path: Path) -> None:
        self.policy: RiskPolicy = load_policy(policy_path)
        self.policy_sha256 = sha256_file(policy_path)

    @property
    def version(self) -> str:
        return self.policy.policy_version

    def score(self, bundle: LoadedBundle, output: InferenceOutput) -> RiskResult:
        manifest = bundle.manifest
        clf = manifest.components.classifier
        anomaly = manifest.components.anomaly_detector
        classified = output.class_probabilities is not None and clf is not None
        scored = output.anomaly_score is not None and anomaly is not None
        return compute_risk(
            self.policy,
            size=output.size,
            class_probabilities=output.class_probabilities if classified else None,
            classes=clf.classes if classified and clf else None,
            benign_class=clf.benign_class if classified and clf else None,
            anomaly_scores=output.anomaly_score if scored else None,
            anomaly_reference=AnomalyReference(**anomaly.reference_points.model_dump()) if scored and anomaly else None,
            is_anomaly=output.is_anomaly if scored else None,
            needs_review=output.needs_review if classified else None,
        )
