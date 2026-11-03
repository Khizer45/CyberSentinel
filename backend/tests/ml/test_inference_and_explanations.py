"""FR-13/FR-14, ML-05: output semantics, anomaly direction, abstention and explanation correctness."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.ml.artifacts import ExpectedBundle, load_bundle, read_registry
from app.ml.constants import EXPLANATION_DISCLAIMER, NEEDS_REVIEW_LABEL, UNCLASSIFIED_LABEL, AnalysisMode
from app.ml.datasets import get_schema
from app.ml.errors import FeatureSchemaError, InferenceError
from app.ml.explain import explain_rows
from app.ml.inference import InferenceEngine
from app.ml.preprocessing import clean_feature_frame
from tests.fixtures.bundles import build_bundle
from tests.fixtures.data import cic_frame, unsw_frame


def load(model_dir: Path, name: str):  # type: ignore[no-untyped-def]
    e = next(b for b in read_registry(model_dir / "registry.json").bundles if b.model_name == name)
    return load_bundle(model_dir, e.path, ExpectedBundle(e.model_name, e.version, e.manifest_sha256), max_artifact_bytes=2**31)


@pytest.fixture(scope="module")
def unsw_bundle(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    root = tmp_path_factory.mktemp("models")
    built = build_bundle(root, family="unsw_nb15", algorithm="random_forest")
    return load(root, built.model_name)


@pytest.fixture(scope="module")
def cic_bundle(tmp_path_factory: pytest.TempPathFactory):  # type: ignore[no-untyped-def]
    root = tmp_path_factory.mktemp("models")
    built = build_bundle(root, family="cicids2017", algorithm="xgboost")
    return load(root, built.model_name)


def features(family: str, rows: int = 60):  # type: ignore[no-untyped-def]
    schema = get_schema("unsw-nb15-flow-v1" if family == "unsw" else "cicids2017-flow-v1")
    raw = unsw_frame(rows, seed=11) if family == "unsw" else cic_frame(rows, seed=11)
    return clean_feature_frame(raw, schema)[0]


def test_combined_output_semantics(unsw_bundle) -> None:  # type: ignore[no-untyped-def]
    out = InferenceEngine(unsw_bundle).predict(features("unsw"), AnalysisMode.COMBINED)
    assert out.class_probabilities.shape == (60, len(unsw_bundle.manifest.components.classifier.classes))
    assert np.allclose(out.class_probabilities.sum(axis=1), 1.0)
    assert np.allclose(out.classifier_score, 1.0 - out.class_probabilities[:, 0])
    assert out.probability is None  # uncalibrated fixture -> probability must stay empty
    assert out.anomaly_score is not None and np.all(out.anomaly_score > 0) and np.all(out.anomaly_score <= 1)
    assert np.array_equal(out.is_anomaly, out.anomaly_score >= unsw_bundle.manifest.components.anomaly_detector.threshold)


def test_anomaly_scores_increase_for_extreme_inputs(unsw_bundle) -> None:  # type: ignore[no-untyped-def]
    frame = features("unsw", 5)
    extreme = frame.copy()
    for column in get_schema("unsw-nb15-flow-v1").numeric_features:
        extreme[column] = extreme[column] * 1e6
    engine = InferenceEngine(unsw_bundle)
    normal = engine.predict(frame, AnalysisMode.ANOMALY).anomaly_score
    unusual = engine.predict(extreme, AnalysisMode.ANOMALY).anomaly_score
    assert np.all(unusual > normal)


def test_anomaly_only_mode_is_unclassified(unsw_bundle) -> None:  # type: ignore[no-untyped-def]
    out = InferenceEngine(unsw_bundle).predict(features("unsw", 10), AnalysisMode.ANOMALY)
    assert set(out.predicted_label) == {UNCLASSIFIED_LABEL} and out.class_probabilities is None


def test_low_confidence_returns_needs_review(tmp_path: Path) -> None:
    built = build_bundle(tmp_path, family="unsw_nb15", algorithm="random_forest", min_confidence=0.99, with_anomaly=False)
    bundle = load(tmp_path, built.model_name)
    out = InferenceEngine(bundle).predict(features("unsw", 80), AnalysisMode.CLASSIFICATION)
    low = out.label_confidence < 0.99
    assert low.any()
    assert set(out.predicted_label[low]) == {NEEDS_REVIEW_LABEL}
    assert not (out.predicted_label[~low] == NEEDS_REVIEW_LABEL).any()
    with pytest.raises(InferenceError):
        InferenceEngine(bundle).predict(features("unsw", 5), AnalysisMode.COMBINED)


def test_missing_feature_fails_closed(unsw_bundle) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(FeatureSchemaError):
        InferenceEngine(unsw_bundle).predict(features("unsw").drop(columns=["rate"]), AnalysisMode.COMBINED)


def test_tree_path_attribution_is_additive(unsw_bundle) -> None:  # type: ignore[no-untyped-def]
    from app.ml.explain.attribution import tree_path_contributions

    engine = InferenceEngine(unsw_bundle)
    out = engine.predict(features("unsw", 30), AnalysisMode.CLASSIFICATION, keep_transformed=True)
    model = unsw_bundle.classifier
    target = out.class_probabilities.argmax(axis=1)
    contrib = tree_path_contributions(model, out.transformed, target)
    root = np.mean([t.tree_.value[0, 0] / t.tree_.value[0, 0].sum() for t in model.estimators_], axis=0)
    expected = out.class_probabilities[np.arange(30), target] - root[target]
    assert np.allclose(contrib.sum(axis=1), expected, atol=1e-9)


def test_xgboost_shap_is_additive(cic_bundle) -> None:  # type: ignore[no-untyped-def]
    import xgboost as xgb

    from app.ml.explain.attribution import xgboost_contributions

    out = InferenceEngine(cic_bundle).predict(features("cic", 20), AnalysisMode.CLASSIFICATION, keep_transformed=True)
    target = out.class_probabilities.argmax(axis=1)
    contrib = xgboost_contributions(cic_bundle.classifier, out.transformed, target)
    margins = cic_bundle.classifier.get_booster().predict(xgb.DMatrix(out.transformed), output_margin=True)
    full = cic_bundle.classifier.get_booster().predict(xgb.DMatrix(out.transformed), pred_contribs=True)
    bias = full[np.arange(20), target, -1]
    assert np.allclose(contrib.sum(axis=1) + bias, margins[np.arange(20), target], atol=1e-4)


@pytest.mark.parametrize("which", ["unsw", "cic"])
def test_explanation_documents(which: str, unsw_bundle, cic_bundle) -> None:  # type: ignore[no-untyped-def]
    bundle = unsw_bundle if which == "unsw" else cic_bundle
    engine = InferenceEngine(bundle)
    frame = features(which, 15)
    out = engine.predict(frame, AnalysisMode.COMBINED, keep_transformed=True)
    docs = explain_rows(bundle, engine.prepare(frame), out, [0, 3], top_k=5)
    for doc in docs.values():
        assert doc["disclaimer"] == EXPLANATION_DISCLAIMER
        assert doc["method"] == ("tree_path_attribution" if which == "unsw" else "xgboost_tree_shap")
        assert doc["method_family"] == "model_attribution" and 0 < len(doc["top_features"]) <= 5
        assert all(f["direction"] in {"supports", "opposes"} for f in doc["top_features"])
        assert doc["reason_codes"] and all("caus" not in r["text"].lower() for r in doc["reason_codes"])
        assert doc["scores_calibrated"] is False
