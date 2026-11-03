"""Chooses which predictions to explain and attaches the risk breakdown (FR-14).

Explanations are computed for alerts (and, by default, for anomalies and needs-review rows) up to
``EXPLAIN_MAX_ROWS_PER_JOB`` per job, highest risk first, to bound cost on large files.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.ml.artifacts.bundle import LoadedBundle
from app.ml.explain import explain_rows
from app.ml.inference import InferenceOutput
from app.ml.risk import RiskPolicy, RiskResult


def select_positions(scope: str, output: InferenceOutput, risk: RiskResult, budget: int) -> list[int]:
    if scope == "none" or budget <= 0 or output.size == 0:
        return []
    if scope == "all":
        mask = np.ones(output.size, dtype=bool)
    else:
        mask = risk.is_alert.copy()
        if scope == "alerts_and_review":
            mask |= output.needs_review
            if output.is_anomaly is not None:
                mask |= output.is_anomaly
    candidates = np.nonzero(mask)[0]
    if candidates.size == 0:
        return []
    order = candidates[np.argsort(-risk.score[candidates], kind="stable")]
    return sorted(order[:budget].tolist())


def explain(
    bundle: LoadedBundle,
    prepared: pd.DataFrame,
    output: InferenceOutput,
    positions: list[int],
    risk: RiskResult,
    policy: RiskPolicy,
    *,
    top_k: int,
) -> dict[int, dict[str, Any]]:
    documents = explain_rows(bundle, prepared, output, positions, top_k=top_k)
    for position, document in documents.items():
        document["risk"] = risk.breakdown(position, policy)
    return documents
