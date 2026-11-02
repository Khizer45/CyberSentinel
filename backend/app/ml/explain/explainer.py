"""Build explanation documents for selected predictions (FR-14).

Each explanation states its method, whether it is a model attribution or a heuristic, the units of the
contributions, the top features with their values and benign baselines, reason codes, and a disclaimer
that attributions are not causal. When the manifest requests a method that does not fit the loaded
estimator, the explainer falls back to the baseline-deviation heuristic and records why.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from app.ml.artifacts.bundle import LoadedBundle
from app.ml.constants import EXPLANATION_DISCLAIMER, ExplanationMethod
from app.ml.explain.attribution import aggregate_to_sources, tree_path_contributions, xgboost_contributions
from app.ml.explain.baseline import deviation_scores
from app.ml.explain.reason_codes import (
    anomaly_reason,
    attribution_reason,
    deviation_reason,
    low_confidence_reason,
)
from app.ml.inference.engine import InferenceOutput

_TREE_ESTIMATORS = {"RandomForestClassifier", "ExtraTreesClassifier", "DecisionTreeClassifier"}


def _clean(value: Any) -> Any:
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, np.integer):
        return int(value)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value if isinstance(value, (int, str, bool)) else str(value)


def resolve_method(bundle: LoadedBundle) -> tuple[ExplanationMethod, str | None]:
    """Return the attribution method usable for this bundle and a fallback reason if downgraded."""
    meta = bundle.manifest.components.classifier
    if meta is None or bundle.classifier is None:
        return ExplanationMethod.BASELINE_DEVIATION, None
    estimator = type(bundle.classifier).__name__
    requested = meta.explanation_method
    if requested == ExplanationMethod.XGBOOST_TREE_SHAP:
        if estimator == "XGBClassifier":
            return requested, None
        return ExplanationMethod.BASELINE_DEVIATION, f"xgboost_tree_shap is not applicable to {estimator}"
    if requested == ExplanationMethod.TREE_PATH_ATTRIBUTION:
        if estimator in _TREE_ESTIMATORS:
            return requested, None
        return ExplanationMethod.BASELINE_DEVIATION, f"tree_path_attribution is not applicable to {estimator}"
    return ExplanationMethod.BASELINE_DEVIATION, None


def explain_rows(
    bundle: LoadedBundle,
    prepared: pd.DataFrame,
    output: InferenceOutput,
    positions: Sequence[int],
    *,
    top_k: int = 8,
) -> dict[int, dict[str, Any]]:
    """Explain the rows at ``positions`` (0-based positions within ``prepared``/``output``).

    ``prepared`` must be the engine-prepared input frame and ``output.transformed`` must be populated
    (``InferenceEngine.predict(..., keep_transformed=True)``).
    """
    if not positions:
        return {}
    manifest = bundle.manifest
    input_names = manifest.features.input_names
    categorical = {f.name for f in manifest.features.input_features if f.dtype == "categorical"}
    references = manifest.features.benign_reference
    clf_meta = manifest.components.classifier
    anomaly_meta = manifest.components.anomaly_detector
    importance = {fi.feature: fi.importance for fi in (clf_meta.global_feature_importance if clf_meta else [])}

    positions_arr = np.asarray(positions, dtype=np.int64)
    method, fallback_reason = resolve_method(bundle)
    classified = output.top_label is not None and clf_meta is not None
    if not classified:
        method = ExplanationMethod.BASELINE_DEVIATION

    source_contrib: np.ndarray | None = None
    units = "robust_z"
    if classified and method != ExplanationMethod.BASELINE_DEVIATION:
        if output.transformed is None:
            raise ValueError("explanations require InferenceEngine.predict(..., keep_transformed=True)")
        assert clf_meta is not None and output.top_label is not None
        class_index = {c: i for i, c in enumerate(clf_meta.classes)}
        target_idx = np.array([class_index[str(label)] for label in output.top_label[positions_arr]], dtype=np.int64)
        subset = output.transformed[positions_arr]
        if method == ExplanationMethod.XGBOOST_TREE_SHAP:
            raw = xgboost_contributions(bundle.classifier, subset, target_idx)
            units = "log_odds"
        else:
            raw = tree_path_contributions(bundle.classifier, subset, target_idx)
            units = "probability"
        source_contrib = aggregate_to_sources(raw, manifest.features.transformed_feature_sources, input_names)

    explanations: dict[int, dict[str, Any]] = {}
    for row_number, position in enumerate(positions_arr.tolist()):
        row = prepared.iloc[position]
        target_label = str(output.top_label[position]) if classified and output.top_label is not None else "anomaly"
        top_features: list[dict[str, Any]] = []
        reasons: list[dict[str, str]] = []

        if source_contrib is not None:
            values = source_contrib[row_number]
            order = np.argsort(-np.abs(values))[:top_k]
            for col in order:
                contribution = float(values[col])
                if contribution == 0.0:
                    continue
                name = input_names[col]
                ref = references.get(name)
                baseline = (ref.mode if name in categorical else ref.median) if ref else None
                top_features.append(
                    {
                        "feature": name,
                        "value": _clean(row[name]),
                        "contribution": round(contribution, 6),
                        "direction": "supports" if contribution > 0 else "opposes",
                        "baseline": _clean(baseline),
                    }
                )
                if len(reasons) < 5:
                    reasons.append(attribution_reason(name, _clean(row[name]), _clean(baseline), contribution, target_label))
            method_family = "model_attribution"
        else:
            scored = deviation_scores(row, input_names, categorical, references, importance)
            scored.sort(key=lambda item: -item[1])
            for name, _weighted, deviation in scored[:top_k]:
                if deviation == 0:
                    continue
                ref = references[name]
                baseline = ref.mode if name in categorical else ref.median
                top_features.append(
                    {
                        "feature": name,
                        "value": _clean(row[name]),
                        "contribution": round(float(deviation), 6),
                        "direction": "above_baseline" if deviation > 0 else "below_baseline",
                        "baseline": _clean(baseline),
                    }
                )
                if len(reasons) < 5:
                    reasons.append(deviation_reason(name, _clean(row[name]), _clean(baseline), deviation, name in categorical))
            method_family = "heuristic"

        anomaly_block = None
        if output.anomaly_score is not None and anomaly_meta is not None and output.is_anomaly is not None:
            score = float(output.anomaly_score[position])
            anomaly_block = {
                "score": round(score, 8),
                "threshold": anomaly_meta.threshold,
                "is_anomaly": bool(output.is_anomaly[position]),
                "score_direction": anomaly_meta.score_direction,
            }
            if output.is_anomaly[position]:
                reasons.insert(0, anomaly_reason(score, anomaly_meta.threshold))
        if output.needs_review[position] and clf_meta is not None and output.label_confidence is not None:
            reasons.insert(
                0,
                low_confidence_reason(float(output.label_confidence[position]), clf_meta.min_confidence, target_label),
            )

        class_scores = None
        if output.class_probabilities is not None and clf_meta is not None:
            probs = output.class_probabilities[position]
            best = np.argsort(-probs)[:3]
            class_scores = [{"label": clf_meta.classes[i], "score": round(float(probs[i]), 6)} for i in best]

        explanations[position] = {
            "method": method.value,
            "method_family": method_family,
            "target_label": target_label,
            "units": units,
            "top_features": top_features,
            "reason_codes": reasons,
            "anomaly": anomaly_block,
            "class_scores": class_scores,
            "scores_calibrated": bool(clf_meta.probability_calibrated) if clf_meta else False,
            "fallback_reason": fallback_reason,
            "disclaimer": EXPLANATION_DISCLAIMER,
        }
    return explanations
