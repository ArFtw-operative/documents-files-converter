"""Document library and ownership (Verso Folio D2: strict per-user isolation)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Blob, Document, DocumentRevision, DocumentStatus, PageVersion, User
from .errors import NotFound, ServiceError
from .storage import StorageError, get_store

PDF_MAGIC = b"%PDF-"


def safe_name(value: str) -> str:
    name = (value or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[^\w .,()\[\]+&@#-]", "_", name, flags=re.UNICODE).strip(" .")
    return (name or "document.pdf")[:200]


def get_owned_document(db: Session, user: User, document_id: str, *, allow_processing: bool = True,
                       for_update: bool = False) -> Document:
    """The single ownership gate. Another user's document is indistinguishable from a missing one."""
    query = select(Document).where(Document.id == document_id, Document.owner_id == user.id,
                                   Document.status != DocumentStatus.deleted)
    if for_update:
        query = query.with_for_update()
    document = db.scalar(query)
    if document is None:
        raise NotFound("Document not found.")
    if not allow_processing and document.status != DocumentStatus.ready:
        raise ServiceError("document_not_ready", "The document is still being prepared.", status=409)
    return document


def usage_bytes(db: Session, user_id: str) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(Blob.size), 0)).where(Blob.owner_id == user_id)) or 0)


def receive_upload(db: Session, user: User, stream: BinaryIO, filename: str) -> Document:
    settings = get_settings()
    store = get_store()
    try:
        temp, _sha, size = store.receive(stream, settings.max_upload_bytes)
    except StorageError as exc:
        raise ServiceError("upload_too_large", str(exc), status=413) from exc
    try:
        with temp.open("rb") as handle:
            head = handle.read(1024)
        if PDF_MAGIC not in head:
            raise ServiceError("not_a_pdf", "Only PDF files can be opened in the editor.", status=415)
        if usage_bytes(db, user.id) + size > user.quota_bytes:
            raise ServiceError("quota_exceeded", "This upload would exceed your storage quota.", status=413)
        blob = store.adopt(db, user.id, temp)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    name = safe_name(filename)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    document = Document(owner_id=user.id, name=name, original_blob_key=blob.key, original_sha256=blob.sha256,
                        size=blob.size, status=DocumentStatus.processing)
    db.add(document)
    db.flush()
    return document


def revision_row(db: Session, document: Document, revision: int | None = None) -> DocumentRevision:
    number = document.current_revision if revision is None else revision
    row = db.scalar(select(DocumentRevision).where(DocumentRevision.document_id == document.id,
                                                   DocumentRevision.revision == number))
    if row is None:
        raise NotFound("Revision not found.")
    return row


def page_version(db: Session, document_id: str, page_id: str, version: int) -> PageVersion:
    row = db.scalar(select(PageVersion).where(PageVersion.page_id == page_id, PageVersion.version == version,
                                              PageVersion.document_id == document_id))
    if row is None:
        raise NotFound("Page not found.")
    return row


def soft_delete(db: Session, document: Document) -> None:
    document.status = DocumentStatus.deleted
    document.deleted_at = datetime.now(UTC)


def document_summary(document: Document) -> dict:
    return {
        "id": document.id, "name": document.name, "status": document.status.value, "error": document.error,
        "page_count": document.page_count, "current_revision": document.current_revision,
        "size": document.size, "info": document.info, "created_at": document.created_at,
        "updated_at": document.updated_at,
    }
