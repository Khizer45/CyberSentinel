"""Human-readable reason codes built from feature-level evidence (never phrased as causes)."""

from __future__ import annotations

import math
from typing import Any


def format_value(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "missing"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def attribution_reason(feature: str, value: Any, baseline: Any, contribution: float, target: str) -> dict[str, str]:
    direction = "increased" if contribution > 0 else "decreased"
    base = f" (typical benign value {format_value(baseline)})" if baseline is not None else ""
    return {
        "code": "ATTRIBUTION_SUPPORTS" if contribution > 0 else "ATTRIBUTION_OPPOSES",
        "feature": feature,
        "text": f"{feature} = {format_value(value)}{base} {direction} the model's score for '{target}'.",
    }


def deviation_reason(feature: str, value: Any, baseline: Any, deviation: float, categorical: bool) -> dict[str, str]:
    if categorical:
        return {
            "code": "UNUSUAL_CATEGORY",
            "feature": feature,
            "text": f"{feature} = '{format_value(value)}' differs from the most common benign value '{format_value(baseline)}'.",
        }
    level = "unusually high" if deviation > 0 else "unusually low"
    return {
        "code": "ABOVE_BENIGN_BASELINE" if deviation > 0 else "BELOW_BENIGN_BASELINE",
        "feature": feature,
        "text": f"{feature} = {format_value(value)} is {level} compared with benign training traffic "
        f"(median {format_value(baseline)}).",
    }


def anomaly_reason(score: float, threshold: float) -> dict[str, str]:
    return {
        "code": "ANOMALY_SCORE_ABOVE_THRESHOLD",
        "feature": "",
        "text": f"Anomaly score {score:.3f} is at or above the model threshold {threshold:.3f}: the flow is unusual "
        "relative to the training traffic. An anomaly is not necessarily an attack.",
    }


def low_confidence_reason(confidence: float, minimum: float, top_label: str) -> dict[str, str]:
    return {
        "code": "LOW_MODEL_CONFIDENCE",
        "feature": "",
        "text": f"The classifier's top class '{top_label}' scored {confidence:.2f}, below the minimum confidence "
        f"{minimum:.2f}; the record needs analyst review.",
    }
