"""Per-document write lock during canonical PDF writes (architecture §54). Reads continue.

PostgreSQL: ``SELECT ... FOR UPDATE`` on the document row (works across API and worker
processes). SQLite (dev/test, single process): an in-process lock per key.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import is_postgres
from ..models import Document, PageVersion

_local_locks: dict[str, threading.RLock] = defaultdict(threading.RLock)
_guard = threading.Lock()


def _local(key: str) -> threading.RLock:
    with _guard:
        return _local_locks[key]


@contextmanager
def document_lock(db: Session, document_id: str) -> Iterator[Document | None]:
    if is_postgres():
        yield db.scalar(select(Document).where(Document.id == document_id).with_for_update())
        return
    with _local(f"doc:{document_id}"):
        db.expire_all()
        yield db.get(Document, document_id)


@contextmanager
def page_version_lock(db: Session, version_id: str) -> Iterator[PageVersion | None]:
    if is_postgres():
        yield db.scalar(select(PageVersion).where(PageVersion.id == version_id).with_for_update())
        return
    with _local(f"pv:{version_id}"):
        db.expire_all()
        yield db.get(PageVersion, version_id)
