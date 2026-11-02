"""Package a model bundle that **the notebooks trained** (this module never trains or fits).

``export_bundle`` serializes already-fitted objects with joblib, derives the feature contract from the fitted
preprocessor, records hashes/runtime versions/measured metrics in a validated manifest, writes golden parity
fixtures and a model card, and registers the bundle in the registry index. The API does not import this
module (enforced by ``tests/architecture``).
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.ml.artifacts.compatibility import current_runtime
from app.ml.artifacts.golden import write_golden
from app.ml.artifacts.integrity import safe_resolve, sha256_bytes, sha256_file
from app.ml.artifacts.loader import bundle_from_objects, qualified_name
from app.ml.artifacts.manifest import (
    MANIFEST_FILENAME,
    AnomalyComponent,
    ArtifactFile,
    BundleInfo,
    BundleManifest,
    ClassifierComponent,
    ComponentsSection,
    DatasetSection,
    FeatureReference,
    FeaturesSection,
    GoldenSection,
    InputFeature,
    PreprocessingSection,
    RegistryEntry,
)
from app.ml.artifacts.registry_io import upsert_entry
from app.ml.constants import ModelType

PREPROCESSOR_FILE = "preprocessor.joblib"
CLASSIFIER_FILE = "classifier.joblib"
ANOMALY_FILE = "anomaly_detector.joblib"
MODEL_CARD_FILE = "model_card.md"


def to_jsonable(value: Any) -> Any:
    """Convert numpy/pandas scalars and containers to JSON-safe Python; NaN/inf become ``None``."""
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def transformed_feature_sources(preprocessor: Any) -> list[str]:
    """Map every output column of a fitted ``ColumnTransformer`` to the input column it derives from."""
    sources: list[str] = []
    for name, transformer, columns in preprocessor.transformers_:
        if transformer == "drop" or (name == "remainder" and transformer == "drop"):
            continue
        cols = [columns] if isinstance(columns, str) else [str(c) for c in columns]
        if not cols:
            continue
        if transformer == "passthrough":
            sources.extend(cols)
            continue
        out_names = [str(n) for n in transformer.get_feature_names_out(cols)]
        if len(out_names) == len(cols) and out_names == cols:
            sources.extend(cols)
            continue
        for out in out_names:
            matches = [c for c in cols if out == c or out.startswith(f"{c}_")]
            if not matches:
                raise ValueError(f"cannot map transformed feature {out!r} to an input column")
            sources.append(max(matches, key=len))
    expected = len(preprocessor.get_feature_names_out())
    if len(sources) != expected:
        raise ValueError(f"mapped {len(sources)} transformed features but the preprocessor outputs {expected}")
    return sources


@dataclass(frozen=True)
class ExportResult:
    bundle_dir: Path
    manifest_path: Path
    manifest_sha256: str
    manifest: BundleManifest
    registry_path: Path | None


def _dump(obj: Any, path: Path) -> ArtifactFile:
    joblib.dump(obj, path, compress=3)
    return ArtifactFile(file=path.name, sha256=sha256_file(path), size_bytes=path.stat().st_size)


def render_model_card(manifest: BundleManifest) -> str:
    """Markdown model card generated from the manifest (Workflow Manual 20: Model Card)."""
    b, d = manifest.bundle, manifest.dataset
    clf, anom = manifest.components.classifier, manifest.components.anomaly_detector
    lines = [
        f"# Model card — {b.model_name} {b.version}",
        "",
        f"*Generated {b.created_at.isoformat()} by {b.created_by}. Metrics below were measured by the training notebooks;",
        "they describe the stated evaluation split only and are not guarantees of production performance.*",
        "",
        "## Intended use",
        f"{b.description}",
        "Decision support for network-flow analysis. Predictions are not proof of compromise and require analyst review.",
        "",
        "## Data",
        f"- Dataset family: `{d.family}` — schema `{d.schema_version}`",
        f"- Source: {d.source}",
        f"- Split strategy: {d.split_strategy} (seed {d.random_seed})",
        f"- Rows: train {d.train_rows:,} / validation {d.validation_rows:,} / test {d.test_rows:,}",
        f"- Label mapping: `{d.label_mapping_version}`" + (f"; class policy: {d.class_policy}" if d.class_policy else ""),
        "",
        "## Components",
        f"- Preprocessing `{manifest.preprocessing.preprocessing_version}`: {manifest.preprocessing.description}",
    ]
    if clf:
        lines.append(
            f"- Classifier `{clf.estimator_class}` ({clf.task}); classes: {', '.join(clf.classes)}; "
            f"calibrated probabilities: {'yes' if clf.probability_calibrated else 'no (scores are uncalibrated)'}; "
            f"min confidence {clf.min_confidence}"
            + (f"; decision threshold {clf.decision_threshold} ({clf.threshold_method})" if clf.decision_threshold else "")
        )
    if anom:
        lines.append(
            f"- Anomaly detector `{anom.estimator_class}` trained on {anom.training_population.replace('_', ' ')} data; "
            f"score = {anom.score_definition}; threshold {anom.threshold:.6f} ({anom.threshold_method})"
        )
    lines += ["", "## Measured metrics", "```json", json.dumps(manifest.metrics, indent=2)[:20000], "```", "", "## Limitations"]
    lines += [f"- {item}" for item in manifest.limitations] or ["- None recorded."]
    lines += [
        "",
        "## Runtime",
        f"Python {manifest.runtime.python}, numpy {manifest.runtime.numpy}, pandas {manifest.runtime.pandas}, "
        f"scikit-learn {manifest.runtime.scikit_learn}, xgboost {manifest.runtime.xgboost}, joblib {manifest.runtime.joblib}",
        "",
    ]
    return "\n".join(lines)


def export_bundle(
    *,
    model_dir: Path,
    model_name: str,
    version: str,
    model_type: ModelType,
    description: str,
    created_by: str,
    dataset: DatasetSection,
    preprocessor: Any,
    preprocessing_version: str,
    preprocessing_description: str,
    preprocessing_steps: list[str],
    input_features: list[InputFeature],
    benign_reference: dict[str, FeatureReference],
    classifier: Any | None = None,
    classifier_meta: dict[str, Any] | None = None,
    anomaly_detector: Any | None = None,
    anomaly_meta: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
    golden_frame: pd.DataFrame | None = None,
    overwrite: bool = False,
    registry_path: Path | None = None,
) -> ExportResult:
    """Serialize fitted objects into ``model_dir/bundles/<model_name>/<version>/`` with a validated manifest.

    ``classifier_meta``/``anomaly_meta`` contain the component fields of :class:`ClassifierComponent` /
    :class:`AnomalyComponent` except ``artifact`` and ``estimator_class`` (filled in here).
    """
    model_dir = model_dir.resolve()
    relative = f"bundles/{model_name}/{version}"
    bundle_dir = safe_resolve(model_dir, relative)
    if bundle_dir.exists():
        if not overwrite:
            raise FileExistsError(f"bundle {relative} already exists; bump the version or pass overwrite=True")
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    preprocessing_file = _dump(preprocessor, bundle_dir / PREPROCESSOR_FILE)
    classifier_component = None
    if classifier is not None:
        if classifier_meta is None:
            raise ValueError("classifier_meta is required when exporting a classifier")
        classifier_component = ClassifierComponent(
            artifact=_dump(classifier, bundle_dir / CLASSIFIER_FILE),
            estimator_class=qualified_name(classifier),
            **classifier_meta,
        )
    anomaly_component = None
    if anomaly_detector is not None:
        if anomaly_meta is None:
            raise ValueError("anomaly_meta is required when exporting an anomaly detector")
        anomaly_component = AnomalyComponent(
            artifact=_dump(anomaly_detector, bundle_dir / ANOMALY_FILE),
            estimator_class=qualified_name(anomaly_detector),
            **anomaly_meta,
        )

    common: dict[str, Any] = {
        "manifest_version": "1.0",
        "bundle": BundleInfo(
            model_name=model_name,
            version=version,
            model_type=model_type,
            description=description,
            created_at=datetime.now(UTC),
            created_by=created_by,
        ),
        "dataset": dataset,
        "features": FeaturesSection(
            feature_schema_version=dataset.schema_version,
            input_features=input_features,
            transformed_feature_names=[str(n) for n in preprocessor.get_feature_names_out()],
            transformed_feature_sources=transformed_feature_sources(preprocessor),
            benign_reference=benign_reference,
        ),
        "preprocessing": PreprocessingSection(
            preprocessing_version=preprocessing_version,
            artifact=preprocessing_file,
            description=preprocessing_description,
            steps=preprocessing_steps,
        ),
        "components": ComponentsSection(classifier=classifier_component, anomaly_detector=anomaly_component),
        "metrics": to_jsonable(metrics or {}),
        "runtime": current_runtime(),
        "limitations": limitations or [],
    }
    manifest = BundleManifest(**common)

    if golden_frame is not None and len(golden_frame):
        in_memory = bundle_from_objects(
            manifest, preprocessor=preprocessor, classifier=classifier, anomaly_detector=anomaly_detector, bundle_dir=bundle_dir
        )
        golden_input, golden_expected, rows = write_golden(in_memory, golden_frame, bundle_dir)
        manifest = BundleManifest(**common, golden=GoldenSection(input=golden_input, expected=golden_expected, rows=rows))

    payload = (json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    manifest_path = bundle_dir / MANIFEST_FILENAME
    manifest_path.write_bytes(payload)
    digest = sha256_bytes(payload)
    (bundle_dir / MODEL_CARD_FILE).write_text(render_model_card(manifest), encoding="utf-8")

    registry = registry_path if registry_path is not None else model_dir / "registry.json"
    upsert_entry(registry, RegistryEntry(model_name=model_name, version=version, path=relative, manifest_sha256=digest))
    return ExportResult(
        bundle_dir=bundle_dir, manifest_path=manifest_path, manifest_sha256=digest, manifest=manifest, registry_path=registry
    )
