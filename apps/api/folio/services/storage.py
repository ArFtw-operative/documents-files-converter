"""Local content-addressed storage (architecture §7.4, §27, §69).

Layout under ``FOLIO_DATA_DIR``::

    blobs/<owner>/<sha[:2]>/<sha>.<ext>   originals, revisions, exports (deduplicated per owner)
    temp/                                 in-flight writes, renamed atomically into blobs/
    failed/                               artifacts that failed validation, kept for diagnostics

Writes always go to ``temp/`` first, are fsynced, then ``os.replace``d into place.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Blob

CHUNK = 1024 * 1024


class StorageError(Exception):
    pass


class BlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        for name in ("blobs", "temp", "failed"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if self.root not in resolved.parents:
            raise StorageError("Unsafe storage key")
        return resolved

    def temp_path(self, suffix: str = ".pdf") -> Path:
        return self.root / "temp" / f"{uuid.uuid4().hex}{suffix}"

    def receive(self, stream: BinaryIO, limit: int) -> tuple[Path, str, int]:
        """Stream an upload into temp/ while hashing; enforces the size limit."""
        target = self.temp_path(".upload")
        digest, size = hashlib.sha256(), 0
        try:
            with target.open("wb") as out:
                while chunk := stream.read(CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise StorageError("The file is larger than the upload limit.")
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target, digest.hexdigest(), size

    def adopt(self, db: Session, owner_id: str, source: Path, kind: str = "pdf", ext: str = "pdf") -> Blob:
        """Move a finished temp file into content-addressed storage and register it."""
        sha, size = _hash_file(source)
        key = f"blobs/{owner_id}/{sha[:2]}/{sha}.{ext}"
        existing = db.get(Blob, key)
        final = self.path(key)
        if existing is not None and final.exists():
            source.unlink(missing_ok=True)
            return existing
        final.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(source, final)
        blob = existing or Blob(key=key, owner_id=owner_id, sha256=sha, size=size, kind=kind)
        if existing is None:
            db.add(blob)
            db.flush()
        return blob

    def keep_failed(self, source: Path, name: str) -> Path:
        target = self.root / "failed" / name
        try:
            shutil.move(str(source), target)
        except OSError:
            source.unlink(missing_ok=True)
        return target

    def remove(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)


def _hash_file(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


_store: BlobStore | None = None


def get_store() -> BlobStore:
    global _store
    if _store is None or _store.root != Path(get_settings().data_dir).resolve():
        _store = BlobStore(get_settings().data_dir)
    return _store
