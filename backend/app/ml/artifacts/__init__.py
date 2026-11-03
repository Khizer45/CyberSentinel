"""Model artifact contract: manifest schema, integrity, compatibility, secure loading, export, golden parity.

Note: :mod:`app.ml.artifacts.export` is intentionally *not* re-exported here; it is used by the notebooks only.
"""

from app.ml.artifacts.bundle import ExpectedBundle, LoadedBundle
from app.ml.artifacts.golden import verify_golden
from app.ml.artifacts.loader import load_bundle, read_manifest
from app.ml.artifacts.manifest import BundleManifest, RegistryEntry, RegistryIndex
from app.ml.artifacts.registry_io import read_registry

__all__ = [
    "BundleManifest",
    "ExpectedBundle",
    "LoadedBundle",
    "RegistryEntry",
    "RegistryIndex",
    "load_bundle",
    "read_manifest",
    "read_registry",
    "verify_golden",
]
