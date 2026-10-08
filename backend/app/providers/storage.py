"""Blob storage behind an interface (local disk now, MinIO-compatible later)."""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def put(self, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...


class LocalStorage:
    """Content-addressed files: the key is the SHA-256 of the bytes, so identical bodies are
    stored once and keys never contain anything a user supplied."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("invalid storage key")
        return self.root / key[:2] / key

    def put(self, data: bytes) -> str:
        key = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)  # atomic: readers never see a partial file
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()
