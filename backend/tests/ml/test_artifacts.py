"""SEC-06 / FR-08: trusted, checksum-verified, compatible artifacts only; fail closed otherwise."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import joblib
import pytest

from app.ml.artifacts import ExpectedBundle, load_bundle, read_registry, verify_golden
from app.ml.artifacts.integrity import sha256_bytes, sha256_file
from app.ml.errors import (
    ArtifactIncompatibleError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactPathError,
    ManifestError,
)
from tests.fixtures.bundles import build_bundle

MAX = 2**31


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    build_bundle(tmp_path, family="unsw_nb15", algorithm="random_forest")
    return tmp_path


def entry(model_dir: Path):  # type: ignore[no-untyped-def]
    return read_registry(model_dir / "registry.json").bundles[0]


def expected(e) -> ExpectedBundle:  # type: ignore[no-untyped-def]
    return ExpectedBundle(e.model_name, e.version, e.manifest_sha256, "unsw-nb15-flow-v1", "unsw_nb15-prep-test")


def rewrite_manifest(model_dir: Path, mutate) -> str:  # type: ignore[no-untyped-def]
    """Mutate manifest.json and return its new hash (simulates an attacker who can also edit the manifest)."""
    path = model_dir / entry(model_dir).path / "manifest.json"
    data = json.loads(path.read_text())
    mutate(data)
    raw = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    return sha256_bytes(raw)


def test_valid_bundle_loads_and_golden_parity_passes(model_dir: Path) -> None:
    bundle = load_bundle(model_dir, entry(model_dir).path, expected(entry(model_dir)), max_artifact_bytes=MAX)
    assert bundle.supports_mode("combined")
    report = verify_golden(bundle)
    assert report["passed"] and report["label_mismatches"] == 0 and report["max_score_abs_diff"] <= 1e-9


def test_tampered_component_file_is_rejected(model_dir: Path) -> None:
    e = entry(model_dir)
    target = model_dir / e.path / "classifier.joblib"
    data = bytearray(target.read_bytes())
    data[-5] ^= 0xFF
    target.write_bytes(bytes(data))
    with pytest.raises(ArtifactIntegrityError):
        load_bundle(model_dir, e.path, expected(e), max_artifact_bytes=MAX)


def test_manifest_hash_must_match_database_pin(model_dir: Path) -> None:
    e = entry(model_dir)
    rewrite_manifest(model_dir, lambda d: d["bundle"].update(description="edited"))
    with pytest.raises(ArtifactIntegrityError):
        load_bundle(model_dir, e.path, expected(e), max_artifact_bytes=MAX)


def test_missing_bundle_and_files(model_dir: Path) -> None:
    e = entry(model_dir)
    (model_dir / e.path / "anomaly_detector.joblib").unlink()
    with pytest.raises(ArtifactNotFoundError):
        load_bundle(model_dir, e.path, expected(e), max_artifact_bytes=MAX)
    shutil.rmtree(model_dir / e.path)
    with pytest.raises(ArtifactNotFoundError):
        load_bundle(model_dir, e.path, expected(e), max_artifact_bytes=MAX)


@pytest.mark.parametrize("bad_path", ["../outside", "/etc", "bundles/../../x", "bundles\\x", ""])
def test_path_traversal_rejected(model_dir: Path, bad_path: str) -> None:
    with pytest.raises(ArtifactPathError):
        load_bundle(model_dir, bad_path, expected(entry(model_dir)), max_artifact_bytes=MAX)


def test_symlink_escape_rejected(model_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside")
    (model_dir / "bundles" / "evil").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ArtifactPathError):
        load_bundle(model_dir, "bundles/evil", expected(entry(model_dir)), max_artifact_bytes=MAX)


def test_incompatible_runtime_rejected(model_dir: Path) -> None:
    e = entry(model_dir)
    new_hash = rewrite_manifest(model_dir, lambda d: d["runtime"].update(scikit_learn="0.24.2"))
    with pytest.raises(ArtifactIncompatibleError) as exc:
        load_bundle(model_dir, e.path, ExpectedBundle(e.model_name, e.version, new_hash), max_artifact_bytes=MAX)
    assert "scikit-learn" in exc.value.details["problems"][0]


def test_unsupported_manifest_version_rejected(model_dir: Path) -> None:
    e = entry(model_dir)
    new_hash = rewrite_manifest(model_dir, lambda d: d.update(manifest_version="9.9"))
    with pytest.raises(ManifestError):
        load_bundle(model_dir, e.path, ExpectedBundle(e.model_name, e.version, new_hash), max_artifact_bytes=MAX)


def test_non_allowlisted_object_rejected_even_with_valid_hashes(model_dir: Path) -> None:
    e = entry(model_dir)
    target = model_dir / e.path / "classifier.joblib"
    joblib.dump({"not": "a model"}, target)
    digest, size = sha256_file(target), target.stat().st_size
    new_hash = rewrite_manifest(
        model_dir, lambda d: d["components"]["classifier"]["artifact"].update(sha256=digest, size_bytes=size)
    )
    with pytest.raises(ArtifactIncompatibleError):
        load_bundle(model_dir, e.path, ExpectedBundle(e.model_name, e.version, new_hash), max_artifact_bytes=MAX)


def test_feature_order_mismatch_fails_closed(model_dir: Path) -> None:
    e = entry(model_dir)

    def swap(d):  # type: ignore[no-untyped-def]
        feats = d["features"]["input_features"]
        feats[0], feats[1] = feats[1], feats[0]

    new_hash = rewrite_manifest(model_dir, swap)
    with pytest.raises(ArtifactIncompatibleError):
        load_bundle(model_dir, e.path, ExpectedBundle(e.model_name, e.version, new_hash), max_artifact_bytes=MAX)


def test_identity_mismatch_rejected(model_dir: Path) -> None:
    e = entry(model_dir)
    with pytest.raises(ArtifactIntegrityError):
        load_bundle(model_dir, e.path, ExpectedBundle("other-model", e.version, e.manifest_sha256), max_artifact_bytes=MAX)
    with pytest.raises(ArtifactIncompatibleError):
        load_bundle(
            model_dir,
            e.path,
            ExpectedBundle(e.model_name, e.version, e.manifest_sha256, "cicids2017-flow-v1"),
            max_artifact_bytes=MAX,
        )


def test_size_limit_enforced(model_dir: Path) -> None:
    e = entry(model_dir)
    with pytest.raises(ArtifactIntegrityError):
        load_bundle(model_dir, e.path, expected(e), max_artifact_bytes=100)
