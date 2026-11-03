"""Local feature-attribution methods for tree models.

* :func:`xgboost_contributions` — exact TreeSHAP values computed natively by XGBoost
  (``pred_contribs=True``) in margin (log-odds) units.
* :func:`tree_path_contributions` — decision-path ("Saabas") attribution for scikit-learn tree ensembles in
  probability units: each split's change in the target-class proportion is credited to the split feature.
  It is an approximation of SHAP and is labelled as such in explanations.

Both return contributions in the *transformed* feature space; :func:`aggregate_to_sources` sums them back to
the original input features (e.g. one-hot columns → their categorical source).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray


def xgboost_contributions(model: Any, transformed: NDArray[np.float64], class_indices: NDArray[np.int64]) -> NDArray[np.float64]:
    """Contributions toward each row's target class (shape ``(n, n_transformed_features)``)."""
    import xgboost as xgb

    booster = model.get_booster()
    matrix = xgb.DMatrix(transformed, feature_names=booster.feature_names)
    contribs = np.asarray(booster.predict(matrix, pred_contribs=True), dtype=np.float64)
    if contribs.ndim == 2:
        # Binary: margin of class 1. Support for class 0 is the negated contribution.
        values = contribs[:, :-1]
        sign = np.where(class_indices == 1, 1.0, -1.0)[:, None]
        return values * sign
    rows = np.arange(contribs.shape[0])
    return contribs[rows, class_indices, :-1]


def _parents(children_left: NDArray[np.int64], children_right: NDArray[np.int64]) -> NDArray[np.int64]:
    parent = np.full(children_left.shape[0], -1, dtype=np.int64)
    for child_array in (children_left, children_right):
        nodes = np.nonzero(child_array >= 0)[0]
        parent[child_array[nodes]] = nodes
    return parent


def tree_path_contributions(
    model: Any, transformed: NDArray[np.float64], class_indices: NDArray[np.int64]
) -> NDArray[np.float64]:
    """Decision-path attribution averaged over the trees of a scikit-learn forest (or a single tree)."""
    estimators = getattr(model, "estimators_", None) or [model]
    n_rows, n_features = transformed.shape
    contributions = np.zeros((n_rows, n_features), dtype=np.float64)
    for estimator in estimators:
        tree = estimator.tree_
        values = np.asarray(tree.value[:, 0, :], dtype=np.float64)
        totals = values.sum(axis=1, keepdims=True)
        values = np.divide(values, totals, out=np.zeros_like(values), where=totals > 0)
        parent = _parents(tree.children_left, tree.children_right)
        path = estimator.decision_path(transformed)
        rows = np.repeat(np.arange(n_rows), np.diff(path.indptr))
        nodes = path.indices
        keep = nodes != 0
        rows, nodes = rows[keep], nodes[keep]
        parents = parent[nodes]
        features = tree.feature[parents]
        target = class_indices[rows]
        delta = values[nodes, target] - values[parents, target]
        np.add.at(contributions, (rows, features), delta)
    return contributions / max(len(estimators), 1)


def aggregate_to_sources(
    contributions: NDArray[np.float64], sources: Sequence[str], input_names: Sequence[str]
) -> NDArray[np.float64]:
    """Sum transformed-feature contributions per original input feature (columns follow ``input_names``)."""
    index = {name: i for i, name in enumerate(input_names)}
    mapping = np.array([index[s] for s in sources], dtype=np.int64)
    out = np.zeros((contributions.shape[0], len(input_names)), dtype=np.float64)
    for transformed_col, source_col in enumerate(mapping):
        out[:, source_col] += contributions[:, transformed_col]
    return out
