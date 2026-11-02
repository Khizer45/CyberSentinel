"""Inference with a verified bundle. Only ``transform``, ``predict_proba`` and ``score_samples`` are called;
nothing is ever fitted here (SEC-07, Workflow Manual 7.4).

Output semantics (FR-13):

* ``class_probabilities`` — the classifier's ``predict_proba`` output (columns follow manifest ``classes``).
* ``classifier_score`` — ``1 − P(benign)``: the raw attack score. It is a *probability* only when the
  manifest declares evaluated calibration, in which case it is also returned as ``probability``.
* ``predicted_label`` — top class; ``needs_review`` when the predicted class's score is below the manifest's
  ``min_confidence``; ``unclassified`` in anomaly-only mode.
* ``anomaly_score`` — ``−score_samples(x)`` (Isolation Forest: in (0, 1], higher = more anomalous);
  ``is_anomaly = anomaly_score ≥ threshold``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from app.ml.artifacts.bundle import LoadedBundle
from app.ml.constants import (
    NEEDS_REVIEW_LABEL,
    UNCLASSIFIED_LABEL,
    AnalysisMode,
    ClassifierTask,
)
from app.ml.errors import FeatureSchemaError, InferenceError


@dataclass
class InferenceOutput:
    size: int
    predicted_label: NDArray[np.object_]
    needs_review: NDArray[np.bool_]
    top_label: NDArray[np.object_] | None = None
    label_confidence: NDArray[np.float64] | None = None
    class_probabilities: NDArray[np.float64] | None = None
    classifier_score: NDArray[np.float64] | None = None
    probability: NDArray[np.float64] | None = None
    anomaly_score: NDArray[np.float64] | None = None
    is_anomaly: NDArray[np.bool_] | None = None
    transformed: NDArray[np.float64] | None = None


class InferenceEngine:
    """Stateless scorer bound to one :class:`LoadedBundle` (safe to share between threads)."""

    def __init__(self, bundle: LoadedBundle) -> None:
        self.bundle = bundle
        self.manifest = bundle.manifest
        self.input_features = self.manifest.features.input_names
        self._categorical = {f.name for f in self.manifest.features.input_features if f.dtype == "categorical"}

    def check_mode(self, mode: AnalysisMode | str) -> AnalysisMode:
        mode = AnalysisMode(mode)
        if not self.bundle.supports_mode(mode):
            raise InferenceError(
                f"the selected model does not support '{mode.value}' analysis",
                details={"supported_modes": self.bundle.supported_modes},
            )
        return mode

    def prepare(self, features: pd.DataFrame) -> pd.DataFrame:
        """Select the manifest's input features in manifest order (fail closed on missing columns)."""
        missing = [name for name in self.input_features if name not in features.columns]
        if missing:
            raise FeatureSchemaError(
                "input is missing features required by the model", details={"missing_features": missing[:50]}
            )
        frame = features.loc[:, self.input_features].copy()
        for name in self.input_features:
            if name in self._categorical:
                frame[name] = frame[name].astype(object)
            else:
                frame[name] = frame[name].astype("float64")
        return frame

    def transform(self, frame: pd.DataFrame) -> NDArray[np.float64]:
        matrix = self.bundle.preprocessor.transform(frame)
        if hasattr(matrix, "toarray"):
            matrix = matrix.toarray()
        matrix = np.asarray(matrix, dtype=np.float64)
        if matrix.shape != (len(frame), len(self.manifest.features.transformed_feature_names)):
            raise InferenceError("the preprocessor produced an unexpected feature matrix shape")
        if not np.isfinite(matrix).all():
            raise InferenceError("the preprocessor produced non-finite values")
        return matrix

    def predict(self, features: pd.DataFrame, mode: AnalysisMode | str, *, keep_transformed: bool = False) -> InferenceOutput:
        mode = self.check_mode(mode)
        frame = self.prepare(features)
        size = len(frame)
        transformed = self.transform(frame)
        output = InferenceOutput(
            size=size,
            predicted_label=np.full(size, UNCLASSIFIED_LABEL, dtype=object),
            needs_review=np.zeros(size, dtype=bool),
            transformed=transformed if keep_transformed else None,
        )

        if mode in (AnalysisMode.CLASSIFICATION, AnalysisMode.COMBINED):
            self._classify(transformed, output)
        if mode in (AnalysisMode.ANOMALY, AnalysisMode.COMBINED):
            self._score_anomaly(transformed, output)
        return output

    def _classify(self, transformed: NDArray[np.float64], output: InferenceOutput) -> None:
        meta = self.manifest.components.classifier
        assert meta is not None and self.bundle.classifier is not None
        proba = np.asarray(self.bundle.classifier.predict_proba(transformed), dtype=np.float64)
        if proba.shape != (output.size, len(meta.classes)):
            raise InferenceError("the classifier returned an unexpected probability matrix")
        proba = np.clip(proba, 0.0, 1.0)
        classes = np.asarray(meta.classes, dtype=object)
        benign_idx = meta.classes.index(meta.benign_class)
        attack_score = np.clip(1.0 - proba[:, benign_idx], 0.0, 1.0)

        if meta.task == ClassifierTask.BINARY:
            assert meta.decision_threshold is not None
            positive_idx = 1 - benign_idx
            positive = proba[:, positive_idx] >= meta.decision_threshold
            top_idx = np.where(positive, positive_idx, benign_idx)
            confidence = np.where(positive, proba[:, positive_idx], proba[:, benign_idx])
        else:
            top_idx = np.argmax(proba, axis=1)
            confidence = proba[np.arange(output.size), top_idx]

        top_label = classes[top_idx]
        needs_review = confidence < meta.min_confidence
        output.class_probabilities = proba
        output.top_label = top_label
        output.label_confidence = confidence
        output.classifier_score = attack_score
        output.probability = attack_score.copy() if meta.probability_calibrated else None
        output.needs_review = needs_review
        output.predicted_label = np.where(needs_review, NEEDS_REVIEW_LABEL, top_label).astype(object)

    def _score_anomaly(self, transformed: NDArray[np.float64], output: InferenceOutput) -> None:
        meta = self.manifest.components.anomaly_detector
        assert meta is not None and self.bundle.anomaly_detector is not None
        scores = -np.asarray(self.bundle.anomaly_detector.score_samples(transformed), dtype=np.float64)
        if scores.shape != (output.size,) or not np.isfinite(scores).all():
            raise InferenceError("the anomaly detector returned invalid scores")
        output.anomaly_score = scores
        output.is_anomaly = scores >= meta.threshold
