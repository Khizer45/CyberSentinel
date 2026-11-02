"""Tiny model bundles for tests.

Estimators are fitted **here, in the test fixture**, on synthetic data, then packaged with the same exporter the
notebooks use. They exist only to exercise loading, inference, risk scoring and the API; their outputs are not
meaningful predictions and are never served outside the test process.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from app.ml.artifacts.export import ExportResult, export_bundle
from app.ml.artifacts.manifest import DatasetSection, FeatureReference, InputFeature
from app.ml.constants import BENIGN_LABEL, ExplanationMethod, ModelType
from app.ml.datasets import DatasetSchema
from app.ml.datasets.cicids2017 import CICIDS2017_SCHEMA
from app.ml.datasets.unsw_nb15 import UNSW_NB15_SCHEMA
from app.ml.preprocessing import clean_feature_frame, normalize_labels, signed_log1p
from tests.fixtures.data import cic_frame, unsw_frame


@dataclass(frozen=True)
class BuiltBundle:
    model_name: str
    version: str
    result: ExportResult
    classes: list[str]


def _preprocessor(schema: DatasetSchema, features: list[str]) -> ColumnTransformer:
    numeric = [f for f in features if schema.feature_dtype(f) == "numeric"]
    categorical = [f for f in features if schema.feature_dtype(f) == "categorical"]
    parts = [
        (
            "num",
            Pipeline(
                [
                    ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
                    ("log", FunctionTransformer(signed_log1p, feature_names_out="one-to-one")),
                    ("scale", StandardScaler()),
                ]
            ),
            numeric,
        )
    ]
    if categorical:
        parts.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
                        ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=5, sparse_output=False)),
                    ]
                ),
                categorical,
            )
        )
    return ColumnTransformer(parts, sparse_threshold=0.0)


def build_bundle(
    model_dir: Path,
    *,
    family: str,
    algorithm: str = "random_forest",
    model_name: str | None = None,
    version: str = "1.0.0",
    with_anomaly: bool = True,
    task: str = "multiclass",
    min_confidence: float = 0.0,
    calibrated: bool = False,
) -> BuiltBundle:
    schema = UNSW_NB15_SCHEMA if family == "unsw_nb15" else CICIDS2017_SCHEMA
    raw = unsw_frame(1200, seed=7) if family == "unsw_nb15" else cic_frame(1200, seed=7)
    features, _ = clean_feature_frame(raw, schema)
    labels = normalize_labels(raw[[c for c in schema.label_columns if c in raw.columns]], schema)
    if task == "binary":
        classes = [BENIGN_LABEL, "Malicious"]
        y = labels.binary.to_numpy()
    else:
        classes = [BENIGN_LABEL, *sorted(set(labels.category) - {BENIGN_LABEL})]
        y = labels.category.map({c: i for i, c in enumerate(classes)}).to_numpy()
    pre = _preprocessor(schema, schema.feature_names)
    X = pre.fit_transform(features)
    if algorithm == "xgboost":
        clf = XGBClassifier(n_estimators=25, max_depth=3, tree_method="hist", random_state=0, n_jobs=1)
        method = ExplanationMethod.XGBOOST_TREE_SHAP
    else:
        clf = RandomForestClassifier(n_estimators=15, random_state=0, n_jobs=1)
        method = ExplanationMethod.TREE_PATH_ATTRIBUTION
    clf.fit(X, y)
    benign = y == 0
    anomaly = None
    anomaly_meta = None
    if with_anomaly:
        anomaly = IsolationForest(n_estimators=30, random_state=0).fit(X[benign])
        scores = -anomaly.score_samples(X[benign])
        threshold = float(np.quantile(scores, 0.95))
        upper = float(max(np.quantile(-anomaly.score_samples(X), 0.999), threshold + 1e-3))
        anomaly_meta = {
            "score_definition": "-IsolationForest.score_samples(x)",
            "threshold": threshold,
            "threshold_method": "95th percentile of benign training scores (test fixture)",
            "reference_points": {
                "benign_median": float(min(np.median(scores), threshold - 1e-6)),
                "threshold": threshold,
                "upper": upper,
            },
            "training_population": "benign_only",
        }
    reference = {}
    for name in schema.feature_names:
        column = features.loc[benign, name].dropna()
        if schema.feature_dtype(name) == "numeric":
            q25, median, q75 = np.quantile(column.to_numpy(dtype=float), [0.25, 0.5, 0.75])
            reference[name] = FeatureReference(median=float(median), q25=float(q25), q75=float(q75))
        else:
            reference[name] = FeatureReference(mode=str(column.value_counts().index[0]), mode_frequency=0.5)
    name = model_name or f"{family.replace('_', '-')}-{algorithm.replace('_', '-')}-{task}-test"
    classifier_meta = {
        "task": task,
        "classes": classes,
        "benign_class": BENIGN_LABEL,
        "min_confidence": min_confidence,
        "explanation_method": method,
        "global_feature_importance": [
            {"feature": f, "importance": 1.0 / (i + 1)} for i, f in enumerate(schema.feature_names[:10])
        ],
    }
    if task == "binary":
        classifier_meta["decision_threshold"] = 0.5
        classifier_meta["threshold_method"] = "fixed 0.5 (test fixture)"
    if calibrated:
        classifier_meta["probability_calibrated"] = True
        classifier_meta["calibration"] = {"method": "test fixture flag", "evaluated_on": "none (fixture)"}
    result = export_bundle(
        model_dir=model_dir,
        model_name=name,
        version=version,
        model_type=ModelType.ENSEMBLE if with_anomaly else ModelType.CLASSIFIER,
        description="Test fixture bundle (synthetic data; not a real model).",
        created_by="backend/tests/fixtures/bundles.py",
        dataset=DatasetSection(
            family=family,
            schema_version=schema.schema_version,
            source="synthetic test fixture",
            split_strategy="none",
            random_seed=0,
            train_rows=len(raw),
            validation_rows=0,
            test_rows=0,
            label_mapping_version=schema.label_mapping_version,
        ),
        preprocessor=pre,
        preprocessing_version=f"{family}-prep-test",
        preprocessing_description="test fixture preprocessing",
        preprocessing_steps=["impute", "signed_log1p", "scale", "onehot"],
        input_features=[
            InputFeature(
                name=f,
                dtype=schema.feature_dtype(f),
                categories=sorted(features[f].dropna().astype(str).unique())
                if schema.feature_dtype(f) == "categorical"
                else None,
            )
            for f in schema.feature_names
        ],
        benign_reference=reference,
        classifier=clf,
        classifier_meta=classifier_meta,
        anomaly_detector=anomaly,
        anomaly_meta=anomaly_meta,
        metrics={"note": "test fixture — no meaningful metrics"},
        limitations=["test fixture"],
        golden_frame=features.head(40),
    )
    return BuiltBundle(model_name=name, version=version, result=result, classes=classes)


def manifest_frame(bundle: BuiltBundle) -> pd.DataFrame:  # pragma: no cover - helper for ad-hoc debugging
    return pd.read_csv(bundle.result.bundle_dir / "golden_input.csv")
