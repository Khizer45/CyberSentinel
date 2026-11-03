"""Read/write the registry index (``MODEL_MANIFEST``, default ``model_artifacts/registry.json``)."""

from __future__ import annotations

import json
from pathlib import Path

from app.ml.artifacts.manifest import RegistryEntry, RegistryIndex

MAX_REGISTRY_BYTES = 1024 * 1024


def read_registry(path: Path) -> RegistryIndex:
    if not path.is_file():
        return RegistryIndex()
    if path.stat().st_size > MAX_REGISTRY_BYTES:
        raise ValueError("registry index is too large")
    return RegistryIndex.model_validate_json(path.read_bytes())


def write_registry(path: Path, index: RegistryIndex) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def upsert_entry(path: Path, entry: RegistryEntry) -> RegistryIndex:
    index = read_registry(path)
    bundles = [b for b in index.bundles if (b.model_name, b.version) != (entry.model_name, entry.version)]
    bundles.append(entry)
    bundles.sort(key=lambda b: (b.model_name, b.version))
    updated = RegistryIndex(registry_version=index.registry_version, bundles=bundles)
    write_registry(path, updated)
    return updated
