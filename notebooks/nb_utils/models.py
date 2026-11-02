"""Candidate model factories and training helpers (training happens only in notebooks)."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from app.ml.constants import BENIGN_LABEL


def class_order(labels: pd.Series, benign: str = BENIGN_LABEL) -> list[str]:
    """Deterministic class order: benign first, then alphabetical (index = encoded label)."""
    classes = sorted(set(labels.astype(str)) - {benign})
    return [benign, *classes] if benign in set(labels.astype(str)) else classes


def encode(labels: pd.Series, classes: list[str]) -> np.ndarray:
    mapping = {c: i for i, c in enumerate(classes)}
    unknown = set(labels.astype(str)) - set(mapping)
    if unknown:
        raise ValueError(f"labels not in class list: {sorted(unknown)}")
    return labels.astype(str).map(mapping).to_numpy(dtype=np.int64)


def balanced_weights(y: np.ndarray) -> np.ndarray:
    return compute_sample_weight(class_weight="balanced", y=y)


def make_logistic_regression(seed: int) -> LogisticRegression:
    return LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)


def make_random_forest(seed: int, n_jobs: int, fast: bool = False) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=40 if fast else 300,
        min_samples_leaf=1,
        class_weight="balanced_subsample",
        n_jobs=n_jobs,
        random_state=seed,
    )


def make_xgboost(seed: int, n_classes: int, n_jobs: int, fast: bool = False) -> XGBClassifier:
    params: dict[str, Any] = {
        "n_estimators": 60 if fast else 800,
        "max_depth": 4 if fast else 8,
        "learning_rate": 0.2 if fast else 0.1,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "tree_method": "hist",
        "n_jobs": n_jobs,
        "random_state": seed,
        "early_stopping_rounds": None if fast else 30,
        "eval_metric": "logloss" if n_classes == 2 else "mlogloss",
    }
    return XGBClassifier(**params)


def make_linear_svm(seed: int) -> CalibratedClassifierCV:
    """Linear SVM wrapped in cross-validated sigmoid calibration so it exposes predict_proba."""
    return CalibratedClassifierCV(LinearSVC(class_weight="balanced", random_state=seed, max_iter=5000), method="sigmoid", cv=3)


def make_isolation_forest(seed: int, n_jobs: int, fast: bool = False) -> IsolationForest:
    return IsolationForest(n_estimators=60 if fast else 300, max_samples="auto", contamination="auto", n_jobs=n_jobs, random_state=seed)


def fit_timed(model: Any, X: np.ndarray, y: np.ndarray | None = None, **fit_kwargs: Any) -> tuple[Any, float]:
    start = time.perf_counter()
    if y is None:
        model.fit(X, **fit_kwargs)
    else:
        model.fit(X, y, **fit_kwargs)
    return model, time.perf_counter() - start


def stratified_indices(y: np.ndarray, n: int, seed: int, *, min_per_class: int = 1) -> np.ndarray:
    """Stratified subsample indices for algorithms that do not scale to the full split.

    Every class keeps at least ``min_per_class`` rows (or all of its rows if it has fewer).
    """
    if len(y) <= n:
        return np.arange(len(y))
    rng = np.random.default_rng(seed)
    chosen = []
    for cls in np.unique(y):
        idx = np.nonzero(y == cls)[0]
        take = max(min_per_class, int(round(len(idx) * n / len(y))))
        chosen.append(rng.choice(idx, size=min(take, len(idx)), replace=False))
    return np.sort(np.concatenate(chosen))
