"""Secure loading of trusted model bundles (SEC-06, SAD 5.3).

Order of checks — any failure stops loading (fail closed):

1. The bundle path is confined to ``MODEL_DIR`` (no absolute paths, ``..`` or symlink escapes).
2. ``manifest.json`` exists, is size-bounded and its SHA-256 equals the hash pinned in the database.
3. The manifest validates against :class:`BundleManifest` (supported version, consistent sections).
4. Name, version, feature-schema and preprocessing versions match the database row.
5. Installed scikit-learn / xgboost / numpy versions are compatible with the exporting environment.
6. Every component file is inside the bundle directory, size-bounded and matches its manifest SHA-256.
7. Only then is ``joblib.load`` called, followed by a class allowlist and interface checks.

``joblib``/pickle deserialization executes code; these checks ensure that only files produced and
recorded by the trusted training pipeline are ever deserialized. They are not a sandbox: never place
files from untrusted sources in ``MODEL_DIR``.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import joblib
from pydantic import ValidationError

from app.ml.artifacts.bundle import ExpectedBundle, LoadedBundle
from app.ml.artifacts.compatibility import compatibility_problems
from app.ml.artifacts.integrity import safe_resolve, sha256_bytes, verify_file
from app.ml.artifacts.manifest import MANIFEST_FILENAME, MAX_MANIFEST_BYTES, ArtifactFile, BundleManifest
from app.ml.errors import (
    ArtifactIncompatibleError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ManifestError,
)
from app.ml.preprocessing.transforms import ALLOWED_TRANSFORM_FUNCTIONS


def qualified_name(obj: Any) -> str:
    cls = obj if isinstance(obj, type) else type(obj)
    return f"{cls.__module__}.{cls.__qualname__}"


def _allowed_types() -> dict[str, tuple[type, ...]]:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import (
        ExtraTreesClassifier,
        HistGradientBoostingClassifier,
        IsolationForest,
        RandomForestClassifier,
    )
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer, MinMaxScaler, OneHotEncoder, RobustScaler, StandardScaler
    from sklearn.semi_supervised import LabelPropagation, LabelSpreading
    from sklearn.svm import LinearSVC
    from sklearn.tree import DecisionTreeClassifier

    classifiers: list[type] = [
        RandomForestClassifier,
        ExtraTreesClassifier,
        DecisionTreeClassifier,
        HistGradientBoostingClassifier,
        LogisticRegression,
        CalibratedClassifierCV,
        LabelSpreading,
        LabelPropagation,
    ]
    try:
        from xgboost import XGBClassifier

        classifiers.append(XGBClassifier)
    except ImportError:  # pragma: no cover - xgboost is a pinned dependency
        pass
    return {
        "preprocessor": (ColumnTransformer, Pipeline),
        "preprocessor_step": (
            Pipeline,
            SimpleImputer,
            StandardScaler,
            RobustScaler,
            MinMaxScaler,
            OneHotEncoder,
            FunctionTransformer,
        ),
        "classifier": tuple(classifiers),
        "calibrated_base": (
            RandomForestClassifier,
            ExtraTreesClassifier,
            DecisionTreeClassifier,
            HistGradientBoostingClassifier,
            LogisticRegression,
            LinearSVC,
            *[c for c in classifiers if c.__name__ == "XGBClassifier"],
        ),
        "anomaly_detector": (IsolationForest,),
    }


def _check_type(obj: Any, allowed: tuple[type, ...], role: str) -> None:
    if type(obj) not in allowed:
        raise ArtifactIncompatibleError(
            f"the {role} artifact has an unsupported type",
            details={"role": role, "type": qualified_name(obj)},
        )


def _function_name(func: Any) -> str:
    module = getattr(func, "__module__", None) or ""
    name = getattr(func, "__qualname__", None) or getattr(func, "__name__", "")
    return f"{module}.{name}"


def _check_preprocessor_tree(obj: Any, allowed_steps: tuple[type, ...], depth: int = 0) -> None:
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import FunctionTransformer

    if depth > 5:
        raise ArtifactIncompatibleError("the preprocessing pipeline is nested too deeply")
    children: Iterable[Any] = ()
    if isinstance(obj, ColumnTransformer):
        children = [trans for _name, trans, _cols in obj.transformers_]
    elif isinstance(obj, Pipeline):
        children = [step for _name, step in obj.steps]
    for child in children:
        if isinstance(child, str):
            if child not in {"drop", "passthrough"}:
                raise ArtifactIncompatibleError("unsupported preprocessing step token", details={"step": child})
            continue
        if type(child) not in allowed_steps and not isinstance(child, ColumnTransformer):
            raise ArtifactIncompatibleError(
                "the preprocessing pipeline contains an unsupported step", details={"type": qualified_name(child)}
            )
        if isinstance(child, FunctionTransformer):
            for func in (child.func, child.inverse_func):
                if func is not None and _function_name(func) not in ALLOWED_TRANSFORM_FUNCTIONS:
                    raise ArtifactIncompatibleError(
                        "the preprocessing pipeline references a non-allowlisted function",
                        details={"function": _function_name(func)},
                    )
        _check_preprocessor_tree(child, allowed_steps, depth + 1)


def _check_interfaces(manifest: BundleManifest, preprocessor: Any, classifier: Any, anomaly: Any) -> None:
    input_names = manifest.features.input_names
    names_in = list(getattr(preprocessor, "feature_names_in_", []))
    if names_in != input_names:
        raise ArtifactIncompatibleError(
            "the preprocessor's input features do not match the manifest (order matters)",
            details={"expected_count": len(input_names), "found_count": len(names_in)},
        )
    try:
        transformed = [str(n) for n in preprocessor.get_feature_names_out()]
    except Exception as exc:  # pragma: no cover - defensive
        raise ArtifactIncompatibleError("the preprocessor cannot report its output features") from exc
    if transformed != manifest.features.transformed_feature_names:
        raise ArtifactIncompatibleError("the preprocessor's output features do not match the manifest")

    n_out = len(transformed)
    if classifier is not None:
        meta = manifest.components.classifier
        assert meta is not None
        if not hasattr(classifier, "predict_proba"):
            raise ArtifactIncompatibleError("the classifier does not provide predict_proba")
        classes = [int(c) if not isinstance(c, str) else c for c in getattr(classifier, "classes_", [])]
        if classes != list(range(len(meta.classes))):
            raise ArtifactIncompatibleError(
                "the classifier must be trained on integer-encoded labels 0..K-1 matching manifest classes"
            )
        n_in = getattr(classifier, "n_features_in_", n_out)
        if int(n_in) != n_out:
            raise ArtifactIncompatibleError("the classifier expects a different number of features")
    if anomaly is not None:
        if not hasattr(anomaly, "score_samples"):
            raise ArtifactIncompatibleError("the anomaly detector does not provide score_samples")
        n_in = getattr(anomaly, "n_features_in_", n_out)
        if int(n_in) != n_out:
            raise ArtifactIncompatibleError("the anomaly detector expects a different number of features")


def read_manifest(model_dir: Path, artifact_uri: str, *, expected_sha256: str | None) -> tuple[BundleManifest, str, Path]:
    """Read and validate a bundle manifest; verify its SHA-256 when ``expected_sha256`` is given."""
    bundle_dir = safe_resolve(model_dir, artifact_uri)
    if not bundle_dir.is_dir():
        raise ArtifactNotFoundError("the model bundle directory is missing", details={"bundle": artifact_uri})
    manifest_path = bundle_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ArtifactNotFoundError("the model manifest is missing", details={"bundle": artifact_uri})
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ManifestError("the model manifest is too large")
    raw = manifest_path.read_bytes()
    digest = sha256_bytes(raw)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ArtifactIntegrityError(
            "the model manifest does not match the checksum recorded at registration", details={"bundle": artifact_uri}
        )
    try:
        manifest = BundleManifest.model_validate_json(raw)
    except ValidationError as exc:
        errors = [{"loc": ".".join(str(p) for p in e["loc"]), "msg": e["msg"]} for e in exc.errors()[:20]]
        raise ManifestError("the model manifest failed validation", details={"errors": errors}) from exc
    return manifest, digest, bundle_dir


def _load_component(bundle_dir: Path, artifact: ArtifactFile, max_bytes: int) -> Any:
    path = safe_resolve(bundle_dir, artifact.file)
    verify_file(path, expected_sha256=artifact.sha256, expected_size=artifact.size_bytes, max_bytes=max_bytes)
    return joblib.load(path)


def load_bundle(
    model_dir: Path, artifact_uri: str, expected: ExpectedBundle, *, max_artifact_bytes: int
) -> LoadedBundle:
    """Verify and load a bundle. See the module docstring for the check sequence."""
    manifest, digest, bundle_dir = read_manifest(model_dir, artifact_uri, expected_sha256=expected.manifest_sha256)

    if (manifest.bundle.model_name, manifest.bundle.version) != (expected.model_name, expected.version):
        raise ArtifactIntegrityError("the manifest identity does not match the registered model version")
    if expected.feature_schema_version and manifest.feature_schema_version != expected.feature_schema_version:
        raise ArtifactIncompatibleError("the manifest feature schema does not match the registered model version")
    if expected.preprocessing_version and manifest.preprocessing_version != expected.preprocessing_version:
        raise ArtifactIncompatibleError("the manifest preprocessing version does not match the registered model")

    uses_xgboost = bool(
        manifest.components.classifier and "xgboost" in manifest.components.classifier.estimator_class.lower()
    )
    problems = compatibility_problems(manifest.runtime, uses_xgboost=uses_xgboost)
    if problems:
        raise ArtifactIncompatibleError("the model was exported with incompatible library versions", details={"problems": problems})

    allowed = _allowed_types()
    preprocessor = _load_component(bundle_dir, manifest.preprocessing.artifact, max_artifact_bytes)
    _check_type(preprocessor, allowed["preprocessor"], "preprocessor")
    _check_preprocessor_tree(preprocessor, allowed["preprocessor_step"])

    classifier = None
    if manifest.components.classifier is not None:
        classifier = _load_component(bundle_dir, manifest.components.classifier.artifact, max_artifact_bytes)
        _check_type(classifier, allowed["classifier"], "classifier")
        if type(classifier).__name__ == "CalibratedClassifierCV":
            base = getattr(classifier, "estimator", None)
            # scikit-learn >= 1.6 calibrates prefit models through FrozenEstimator(estimator).
            if type(base).__name__ == "FrozenEstimator":
                base = getattr(base, "estimator", None)
            if base is None:
                raise ArtifactIncompatibleError("the calibrated classifier has no base estimator")
            _check_type(base, allowed["calibrated_base"], "calibrated base estimator")

    anomaly = None
    if manifest.components.anomaly_detector is not None:
        anomaly = _load_component(bundle_dir, manifest.components.anomaly_detector.artifact, max_artifact_bytes)
        _check_type(anomaly, allowed["anomaly_detector"], "anomaly detector")

    _check_interfaces(manifest, preprocessor, classifier, anomaly)
    return LoadedBundle(
        manifest=manifest,
        manifest_sha256=digest,
        bundle_dir=bundle_dir,
        preprocessor=preprocessor,
        classifier=classifier,
        anomaly_detector=anomaly,
    )


def bundle_from_objects(
    manifest: BundleManifest, *, preprocessor: Any, classifier: Any | None, anomaly_detector: Any | None, bundle_dir: Path
) -> LoadedBundle:
    """Wrap in-memory objects (used by the exporter to compute golden outputs before serialization checks)."""
    _check_interfaces(manifest, preprocessor, classifier, anomaly_detector)
    return LoadedBundle(
        manifest=manifest,
        manifest_sha256="0" * 64,
        bundle_dir=bundle_dir,
        preprocessor=preprocessor,
        classifier=classifier,
        anomaly_detector=anomaly_detector,
    )
