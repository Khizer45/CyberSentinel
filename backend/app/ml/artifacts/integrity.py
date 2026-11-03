"""Hashing and path-confinement helpers for trusted model artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from app.ml.errors import ArtifactIntegrityError, ArtifactNotFoundError, ArtifactPathError

_CHUNK = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def safe_resolve(base: Path, relative: str) -> Path:
    """Resolve ``relative`` inside ``base`` and refuse anything that escapes it.

    Rejects absolute paths, ``..`` components, backslashes and symlinks that resolve outside ``base``.
    """
    if not relative or "\\" in relative or "\x00" in relative:
        raise ArtifactPathError("invalid artifact path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"..", ""} for part in pure.parts):
        raise ArtifactPathError("artifact paths must be relative and must not contain '..'")
    base_resolved = base.resolve()
    candidate = (base_resolved / pure).resolve()
    if not candidate.is_relative_to(base_resolved):
        raise ArtifactPathError("artifact path escapes the trusted model directory")
    return candidate


def verify_file(path: Path, *, expected_sha256: str, expected_size: int | None, max_bytes: int) -> None:
    """Check existence, size bounds and SHA-256 of an artifact file before it is deserialized."""
    if not path.is_file():
        raise ArtifactNotFoundError("a model artifact file is missing", details={"file": path.name})
    size = path.stat().st_size
    if size > max_bytes:
        raise ArtifactIntegrityError("a model artifact file exceeds the configured size limit", details={"file": path.name})
    if expected_size is not None and size != expected_size:
        raise ArtifactIntegrityError("a model artifact file has an unexpected size", details={"file": path.name})
    if sha256_file(path) != expected_sha256:
        raise ArtifactIntegrityError("a model artifact file failed checksum verification", details={"file": path.name})
