"""Opaque-key file storage for uploaded datasets (SEC-04).

User-supplied file names are never used in paths. Files are written with owner-only permissions under
``UPLOAD_DIR/<2-char shard>/<random key>.csv`` while their size and SHA-256 are computed in one pass.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.errors import PayloadTooLargeError

_CHUNK = 1024 * 1024
_KEY_LENGTH = 32


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    size_bytes: int
    sha256: str


class UploadStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):  # e.g. Windows ACLs
            os.chmod(self.root, 0o700)

    def path_for(self, storage_key: str) -> Path:
        if len(storage_key) != _KEY_LENGTH or not all(c in "0123456789abcdef" for c in storage_key):
            raise ValueError("invalid storage key")
        return self.root / storage_key[:2] / f"{storage_key}.csv"

    def save_stream(self, source: BinaryIO, *, max_bytes: int) -> StoredFile:
        self._ensure_root()
        key = secrets.token_hex(_KEY_LENGTH // 2)
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(target, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                while chunk := source.read(_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise PayloadTooLargeError()
                    digest.update(chunk)
                    handle.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return StoredFile(storage_key=key, size_bytes=size, sha256=digest.hexdigest())

    def save_local_copy(self, source_path: Path, *, max_bytes: int) -> StoredFile:
        with source_path.open("rb") as handle:
            return self.save_stream(handle, max_bytes=max_bytes)

    def delete(self, storage_key: str | None) -> None:
        if not storage_key:
            return
        try:
            self.path_for(storage_key).unlink(missing_ok=True)
        except ValueError:
            return

    def sha256(self, storage_key: str) -> str | None:
        path = self.path_for(storage_key)
        if not path.is_file():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
        return digest.hexdigest()
