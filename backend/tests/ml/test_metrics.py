"""ML-03/ML-04 metric helpers return real values or None when undefined (never invented)."""

from __future__ import annotations

import numpy as np

from app.ml.evaluation import metrics as M


def test_binary_counts_and_rates() -> None:
    result = M.binary_counts([0, 0, 1, 1, 1], [0, 1, 1, 1, 0])
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (2, 1, 1, 1)
    assert result["precision"] == round(2 / 3, 6) and result["false_positive_rate"] == 0.5


def test_undefined_metrics_are_none() -> None:
    assert M.roc_auc_safe([1, 1, 1], [0.2, 0.4, 0.9]) is None
    assert M.pr_auc_safe([0, 0], [0.1, 0.2]) is None
    assert M.false_alarm_rate(["DoS"], ["DoS"], "Benign") is None


def test_streaming_confusion_matches_batch() -> None:
    truth = ["Benign", "DoS", "DoS", "Benign", "PortScan"]
    pred = ["Benign", "DoS", "Benign", "DoS", "PortScan"]
    stream = M.StreamingConfusion()
    stream.update(truth[:2], pred[:2])
    stream.update(truth[2:], pred[2:])
    report = stream.report("Benign")
    batch = M.classification_report_dict(truth, pred)
    assert report["macro"] == batch["macro"]
    assert report["false_alarm_rate"] == 0.5
    assert report["confusion_matrix"]["labels"] == ["Benign", "DoS", "PortScan"]


def test_threshold_selection_uses_supplied_analysis() -> None:
    y = np.array([0, 0, 0, 1, 1, 1])
    s = np.array([0.1, 0.2, 0.6, 0.55, 0.8, 0.9])
    analysis = M.threshold_analysis(y, s, thresholds=[0.3, 0.5, 0.7])
    # 0.3 and 0.5 tie on F1; ties resolve to the lower (more sensitive) threshold.
    assert M.select_threshold(analysis, strategy="max_f1")["threshold"] == 0.3
    assert M.select_threshold(analysis, strategy="fpr_at_most", max_fpr=0.0)["threshold"] == 0.7


def test_anomaly_metrics_per_category() -> None:
    result = M.anomaly_detection_metrics([0, 0, 1, 1], [0.1, 0.7, 0.8, 0.2], 0.5, ["Benign", "Benign", "DoS", "DoS"])
    assert result["at_threshold"]["false_positive_rate"] == 0.5
    assert result["flag_rate_by_category"]["DoS"]["flag_rate"] == 0.5
