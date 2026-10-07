"""Operation submission, undo/redo and restore (architecture §23, §24, §30).

Undo/redo/restore never re-render a PDF: each creates a new revision that points at an earlier
revision's blob and page map, so the original appearance (and scene ids) return exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pdf_core.mutation.engine import SUPPORTED_OPERATIONS

from ..models import BatchStatus, Document, DocumentOperation, DocumentRevision, OperationBatch, User
from . import audit, events
from .engine_runner import P0_EDIT, run
from .errors import ENGINE_STATUS, Conflict, NotFound, ServiceError
from .locks import document_lock

MAX_OPERATIONS_PER_BATCH = 500


def submit(db: Session, user: User, document: Document, base_revision: int, client_batch_id: str,
           operations: list[dict]) -> OperationBatch:
    if not operations or len(operations) > MAX_OPERATIONS_PER_BATCH:
        raise ServiceError("invalid_payload", f"Send between 1 and {MAX_OPERATIONS_PER_BATCH} operations.", status=422)
    existing = db.scalar(select(OperationBatch).where(OperationBatch.document_id == document.id,
                                                      OperationBatch.client_batch_id == client_batch_id))
    if existing is not None:  # idempotent replay from IndexedDB recovery (§69)
        return existing
    current_map = {entry["page_id"] for entry in _current(db, document).page_map}
    for op in operations:
        if op["type"] not in SUPPORTED_OPERATIONS:
            raise ServiceError("unsupported_operation", f"Unsupported operation: {op['type']}", status=422)
        if op.get("page_id") and op["page_id"] not in current_map and base_revision == document.current_revision:
            raise NotFound("Page not found.")
    batch = OperationBatch(document_id=document.id, client_batch_id=client_batch_id, base_revision=base_revision,
                           created_by=user.id)
    db.add(batch)
    db.flush()
    for sequence, op in enumerate(operations):
        db.add(DocumentOperation(batch_id=batch.id, document_id=document.id, sequence=sequence,
                                 page_id=op.get("page_id"), operation_type=op["type"],
                                 target_ids=op.get("target_ids") or [], payload=op.get("payload") or {},
                                 created_by=user.id))
    db.commit()
    events.publish(document.id, "operation.accepted", batch_id=batch.id, base_revision=base_revision)
    return batch


def commit(db: Session, batch: OperationBatch) -> OperationBatch:
    run("commit_batch", batch.id, queue="pdf_mutation", priority=P0_EDIT)
    db.expire_all()
    return db.get(OperationBatch, batch.id)


def raise_for_failure(batch: OperationBatch) -> None:
    if batch.status != BatchStatus.failed:
        return
    error = batch.error or {}
    code = error.get("code", "engine_error")
    raise ServiceError(code, error.get("message", "The edit failed."), error.get("details"),
                       status=ENGINE_STATUS.get(code, 500))


def _current(db: Session, document: Document) -> DocumentRevision:
    return db.scalar(select(DocumentRevision).where(DocumentRevision.document_id == document.id,
                                                    DocumentRevision.revision == document.current_revision))


def _copy_revision(db: Session, document: Document, source_revision: int, kind: str, batch_id: str,
                   user: User) -> int:
    source = db.scalar(select(DocumentRevision).where(DocumentRevision.document_id == document.id,
                                                      DocumentRevision.revision == source_revision))
    if source is None:
        raise NotFound("Revision not found.")
    new_revision = document.current_revision + 1
    db.add(DocumentRevision(document_id=document.id, revision=new_revision, parent_revision=document.current_revision,
                            blob_key=source.blob_key, sha256=source.sha256, size=source.size,
                            page_map=[dict(e) for e in source.page_map], kind=kind, batch_id=batch_id,
                            validation={"copied_from": source_revision, **(source.validation or {})},
                            created_by=user.id))
    document.current_revision = new_revision
    document.page_count = len(source.page_map)
    document.size = source.size
    document.updated_at = datetime.now(UTC)
    return new_revision


def _expect(document: Document, expected_revision: int | None) -> None:
    if expected_revision is not None and expected_revision != document.current_revision:
        raise Conflict("revision_conflict", "The document changed. Reload to continue.",
                       {"current_revision": document.current_revision})


def undo(db: Session, user: User, document_id: str, expected_revision: int | None) -> dict:
    with document_lock(db, document_id) as document:
        _expect(document, expected_revision)
        batch = db.scalar(select(OperationBatch).where(
            OperationBatch.document_id == document.id, OperationBatch.status == BatchStatus.committed,
            OperationBatch.undone.is_(False), OperationBatch.discarded.is_(False))
            .order_by(OperationBatch.committed_at.desc()).limit(1))
        if batch is None:
            raise ServiceError("nothing_to_undo", "There is nothing to undo.", status=409)
        before = document.current_revision
        revision = _copy_revision(db, document, batch.source_revision, "undo", batch.id, user)
        batch.undone = True
        audit.record(db, "document.undo", user.id, document_id=document.id, batch_id=batch.id,
                     revision_before=before, revision_after=revision)
        db.commit()
    events.publish(document_id, "revision.created", revision=revision, kind="undo", batch_id=batch.id)
    return {"revision": revision, "batch_id": batch.id}


def redo(db: Session, user: User, document_id: str, expected_revision: int | None) -> dict:
    with document_lock(db, document_id) as document:
        _expect(document, expected_revision)
        batch = db.scalar(select(OperationBatch).where(
            OperationBatch.document_id == document.id, OperationBatch.status == BatchStatus.committed,
            OperationBatch.undone.is_(True), OperationBatch.discarded.is_(False))
            .order_by(OperationBatch.committed_at.asc()).limit(1))
        if batch is None:
            raise ServiceError("nothing_to_redo", "There is nothing to redo.", status=409)
        before = document.current_revision
        revision = _copy_revision(db, document, batch.result_revision, "redo", batch.id, user)
        batch.undone = False
        audit.record(db, "document.redo", user.id, document_id=document.id, batch_id=batch.id,
                     revision_before=before, revision_after=revision)
        db.commit()
    events.publish(document_id, "revision.created", revision=revision, kind="redo", batch_id=batch.id)
    return {"revision": revision, "batch_id": batch.id}


def restore(db: Session, user: User, document_id: str, target_revision: int, expected_revision: int | None) -> dict:
    """Restore an earlier revision as a new, undoable revision."""
    with document_lock(db, document_id) as document:
        _expect(document, expected_revision)
        if target_revision == document.current_revision:
            raise ServiceError("already_current", "That revision is already current.", status=409)
        batch = OperationBatch(document_id=document.id, client_batch_id=f"restore:{datetime.now(UTC).timestamp()}",
                               kind="restore", base_revision=document.current_revision,
                               source_revision=document.current_revision, restore_revision=target_revision,
                               status=BatchStatus.committed, created_by=user.id)
        db.add(batch)
        db.flush()
        before = document.current_revision
        revision = _copy_revision(db, document, target_revision, "restore", batch.id, user)
        batch.result_revision = revision
        batch.committed_at = datetime.now(UTC)
        db.execute(update(OperationBatch).where(OperationBatch.document_id == document.id,
                                                OperationBatch.undone.is_(True),
                                                OperationBatch.discarded.is_(False)).values(discarded=True))
        audit.record(db, "document.restore", user.id, document_id=document.id, restored=target_revision,
                     revision_before=before, revision_after=revision)
        db.commit()
    events.publish(document_id, "revision.created", revision=revision, kind="restore")
    return {"revision": revision, "batch_id": batch.id}


def history_state(db: Session, document: Document) -> dict:
    can_undo = db.scalar(select(OperationBatch.id).where(
        OperationBatch.document_id == document.id, OperationBatch.status == BatchStatus.committed,
        OperationBatch.undone.is_(False), OperationBatch.discarded.is_(False)).limit(1)) is not None
    can_redo = db.scalar(select(OperationBatch.id).where(
        OperationBatch.document_id == document.id, OperationBatch.status == BatchStatus.committed,
        OperationBatch.undone.is_(True), OperationBatch.discarded.is_(False)).limit(1)) is not None
    return {"can_undo": can_undo, "can_redo": can_redo}
