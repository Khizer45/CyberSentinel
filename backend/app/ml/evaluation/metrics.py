"""Evaluation metrics (ML-03, ML-04).

All functions return plain JSON-serializable Python types. Metrics that are mathematically undefined for
the given data (e.g. ROC-AUC when only one class is present) are returned as ``None`` — never as a
fabricated number.
"""

from __future__ import annotations

import io
import math
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from typing import Any

import joblib
import numpy as np
from numpy.typing import ArrayLike
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)


def _f(value: float | np.floating | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) or math.isinf(value) else round(value, 6)


def classification_report_dict(y_true: ArrayLike, y_pred: ArrayLike, labels: Sequence[str] | None = None) -> dict[str, Any]:
    """Per-class precision/recall/F1/support plus macro and weighted averages and accuracy."""
    y_true = np.asarray(y_true, dtype=object)
    y_pred = np.asarray(y_pred, dtype=object)
    if labels is None:
        labels = sorted(set(y_true.tolist()) | set(y_pred.tolist()))
    labels = list(labels)
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    per_class = {
        str(label): {"precision": _f(p[i]), "recall": _f(r[i]), "f1": _f(f[i]), "support": int(s[i])}
        for i, label in enumerate(labels)
    }
    report: dict[str, Any] = {"per_class": per_class, "accuracy": _f(np.mean(y_true == y_pred)) if len(y_true) else None}
    for average in ("macro", "weighted"):
        pa, ra, fa, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels, average=average, zero_division=0)
        report[average] = {"precision": _f(pa), "recall": _f(ra), "f1": _f(fa)}
    report["labels"] = [str(label) for label in labels]
    report["samples"] = int(len(y_true))
    return report


def confusion(y_true: ArrayLike, y_pred: ArrayLike, labels: Sequence[str]) -> dict[str, Any]:
    matrix = confusion_matrix(np.asarray(y_true, dtype=object), np.asarray(y_pred, dtype=object), labels=list(labels))
    return {"labels": [str(label) for label in labels], "matrix": matrix.astype(int).tolist()}


def binary_counts(y_true: ArrayLike, y_pred: ArrayLike) -> dict[str, Any]:
    """Binary confusion counts and derived rates; positive class = malicious (1)."""
    t = np.asarray(y_true, dtype=int)
    p = np.asarray(y_pred, dtype=int)
    tp = int(np.sum((t == 1) & (p == 1)))
    fp = int(np.sum((t == 0) & (p == 1)))
    tn = int(np.sum((t == 0) & (p == 0)))
    fn = int(np.sum((t == 1) & (p == 0)))
    return counts_to_rates(tp=tp, fp=fp, tn=tn, fn=fn)


def counts_to_rates(*, tp: int, fp: int, tn: int, fn: int) -> dict[str, Any]:
    def ratio(a: int, b: int) -> float | None:
        return _f(a / b) if b else None

    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    f1 = _f(2 * precision * recall / (precision + recall)) if precision and recall else (0.0 if precision == 0 or recall == 0 else None)
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": ratio(fp, fp + tn),
        "false_negative_rate": ratio(fn, fn + tp),
        "specificity": ratio(tn, tn + fp),
    }


def false_alarm_rate(y_true_labels: ArrayLike, y_pred_labels: ArrayLike, benign_label: str) -> float | None:
    """Fraction of truly benign flows predicted as anything other than benign (multi-class FPR)."""
    t = np.asarray(y_true_labels, dtype=object)
    p = np.asarray(y_pred_labels, dtype=object)
    benign = t == benign_label
    return _f(np.mean(p[benign] != benign_label)) if benign.any() else None


def roc_auc_safe(y_true_binary: ArrayLike, scores: ArrayLike) -> float | None:
    y = np.asarray(y_true_binary, dtype=int)
    if len(np.unique(y)) < 2:
        return None
    return _f(roc_auc_score(y, np.asarray(scores, dtype=float)))


def pr_auc_safe(y_true_binary: ArrayLike, scores: ArrayLike) -> float | None:
    y = np.asarray(y_true_binary, dtype=int)
    if y.sum() == 0:
        return None
    return _f(average_precision_score(y, np.asarray(scores, dtype=float)))


def multiclass_roc_auc_ovr(y_true: ArrayLike, proba: np.ndarray, classes: Sequence[str]) -> dict[str, Any]:
    """One-vs-rest ROC-AUC per class; classes absent from ``y_true`` (or present in every row) are skipped."""
    y = np.asarray(y_true, dtype=object)
    per_class: dict[str, float | None] = {}
    for i, label in enumerate(classes):
        positives = y == label
        per_class[str(label)] = roc_auc_safe(positives.astype(int), proba[:, i]) if 0 < positives.sum() < len(y) else None
    valid = [v for v in per_class.values() if v is not None]
    return {"per_class": per_class, "macro": _f(np.mean(valid)) if valid else None, "classes_evaluated": len(valid)}


def threshold_analysis(y_true_binary: ArrayLike, scores: ArrayLike, thresholds: Iterable[float] | None = None) -> list[dict[str, Any]]:
    """Precision/recall/F1/FPR at each threshold (``score ≥ t`` → malicious)."""
    y = np.asarray(y_true_binary, dtype=int)
    s = np.asarray(scores, dtype=float)
    grid = list(thresholds) if thresholds is not None else [round(x, 3) for x in np.linspace(0.05, 0.95, 19)]
    rows = []
    for t in grid:
        row = binary_counts(y, (s >= t).astype(int))
        row["threshold"] = float(t)
        rows.append(row)
    return rows


def select_threshold(analysis: list[dict[str, Any]], *, strategy: str = "max_f1", max_fpr: float = 0.01) -> dict[str, Any]:
    """Pick an operating threshold from a **validation** threshold analysis."""
    if not analysis:
        raise ValueError("empty threshold analysis")
    if strategy == "max_f1":
        return max(analysis, key=lambda r: (r["f1"] or 0.0, -(r["threshold"])))
    if strategy == "fpr_at_most":
        feasible = [r for r in analysis if r["false_positive_rate"] is not None and r["false_positive_rate"] <= max_fpr]
        if not feasible:
            return min(analysis, key=lambda r: r["false_positive_rate"] if r["false_positive_rate"] is not None else 1.0)
        return max(feasible, key=lambda r: (r["recall"] or 0.0, -(r["threshold"])))
    raise ValueError(f"unknown strategy {strategy!r}")


def anomaly_detection_metrics(
    y_true_binary: ArrayLike, anomaly_scores: ArrayLike, threshold: float, categories: ArrayLike | None = None
) -> dict[str, Any]:
    """Anomaly-score quality vs. ground truth. Higher score = more anomalous; anomalies are not attacks by definition."""
    y = np.asarray(y_true_binary, dtype=int)
    s = np.asarray(anomaly_scores, dtype=float)
    flagged = (s >= threshold).astype(int)
    result: dict[str, Any] = {
        "threshold": float(threshold),
        "roc_auc": roc_auc_safe(y, s),
        "pr_auc": pr_auc_safe(y, s),
        "at_threshold": binary_counts(y, flagged),
        "flag_rate": _f(flagged.mean()) if len(flagged) else None,
    }
    if categories is not None:
        cats = np.asarray(categories, dtype=object)
        result["flag_rate_by_category"] = {
            str(c): {"flag_rate": _f(flagged[cats == c].mean()), "support": int((cats == c).sum())}
            for c in sorted(set(cats.tolist()))
        }
    return result


class StreamingConfusion:
    """Accumulates label pairs across chunks (used for analysis jobs whose upload contains ground truth)."""

    def __init__(self) -> None:
        self.pairs: Counter[tuple[str, str]] = Counter()

    def update(self, y_true: Iterable[str], y_pred: Iterable[str]) -> None:
        self.pairs.update(zip((str(t) for t in y_true), (str(p) for p in y_pred), strict=True))

    @property
    def total(self) -> int:
        return sum(self.pairs.values())

    def report(self, benign_label: str) -> dict[str, Any] | None:
        if not self.pairs:
            return None
        y_true: list[str] = []
        y_pred: list[str] = []
        for (t, p), n in self.pairs.items():
            y_true.extend([t] * n)
            y_pred.extend([p] * n)
        labels = sorted(set(y_true) | set(y_pred))
        report = classification_report_dict(y_true, y_pred, labels)
        report["confusion_matrix"] = confusion(y_true, y_pred, labels)
        t_bin = np.array([0 if t == benign_label else 1 for t in y_true])
        p_bin = np.array([0 if p == benign_label else 1 for p in y_pred])
        report["binary"] = binary_counts(t_bin, p_bin)
        report["false_alarm_rate"] = false_alarm_rate(y_true, y_pred, benign_label)
        return report


def measure_latency(predict: Callable[[Any], Any], data: Any, *, repeats: int = 3) -> dict[str, Any]:
    """Median wall-clock latency of ``predict(data)``; reports ms per record and records per second."""
    n = len(data)
    timings = []
    for _ in range(max(repeats, 1)):
        start = time.perf_counter()
        predict(data)
        timings.append(time.perf_counter() - start)
    median = float(np.median(timings))
    return {
        "records": n,
        "median_seconds": _f(median),
        "ms_per_record": _f(1000 * median / n) if n else None,
        "records_per_second": _f(n / median) if median > 0 else None,
    }


def serialized_size_bytes(obj: Any) -> int:
    buffer = io.BytesIO()
    joblib.dump(obj, buffer, compress=3)
    return buffer.getbuffer().nbytes
