"""Documents, pages, scenes, revisions, operations, undo/redo, exports (architecture §28)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import BatchStatus, DocumentRevision, Export, OperationBatch, PageVersion, SceneObjectRow, User
from ..security.deps import Principal, current_principal, current_user
from ..services import audit, documents, editing
from ..services.engine_runner import P1_VISIBLE, P2_NEARBY, P3_BACKGROUND, enqueue, run
from ..services.errors import NotFound, ServiceError
from ..services.scenes import load_scene, public_scene
from ..services.storage import get_store

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

OperationType = Literal["replace_text", "add_text", "delete_object", "rotate_page", "delete_page",
                        "reorder_page", "insert_page"]


class OperationIn(BaseModel):
    type: OperationType
    page_id: str | None = Field(default=None, max_length=36)
    target_ids: list[str] = Field(default_factory=list, max_length=50)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def bounded(cls, value: dict) -> dict:
        if len(repr(value)) > 20_000:
            raise ValueError("payload too large")
        return value


class OperationBatchIn(BaseModel):
    base_revision: int = Field(ge=1)
    client_batch_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_:\-]+$")
    operations: list[OperationIn] = Field(min_length=1, max_length=500)


class RevisionGuard(BaseModel):
    expected_revision: int | None = None


class Rename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ExportIn(BaseModel):
    mode: Literal["standard", "optimized"] = "standard"
    revision: int | None = None


class AnalyzeIn(BaseModel):
    page_ids: list[str] = Field(default_factory=list, max_length=20)
    priority: Literal["visible", "nearby", "background"] = "visible"


def _pages(db: Session, document, revision: DocumentRevision) -> list[dict]:
    pages = []
    for index, entry in enumerate(revision.page_map):
        version = db.scalar(select(PageVersion).where(PageVersion.page_id == entry["page_id"],
                                                      PageVersion.version == entry["version"]))
        pages.append({"index": index, "page_id": entry["page_id"], "version": entry["version"],
                      "width_pt": version.width_pt if version else None,
                      "height_pt": version.height_pt if version else None,
                      "rotation": version.rotation if version else None,
                      "page_type": version.page_type if version else None,
                      "analysis_status": version.analysis_status if version else "pending"})
    return pages


def _detail(db: Session, document) -> dict:
    data = documents.document_summary(document)
    if document.current_revision:
        data["pages"] = _pages(db, document, documents.revision_row(db, document))
        data.update(editing.history_state(db, document))
    else:
        data["pages"], data["can_undo"], data["can_redo"] = [], False, False
    return data


@router.get("")
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..models import Document, DocumentStatus

    rows = db.scalars(select(Document).where(Document.owner_id == user.id, Document.status != DocumentStatus.deleted)
                      .order_by(Document.updated_at.desc()).limit(500))
    return {"documents": [documents.document_summary(d) for d in rows],
            "usage_bytes": documents.usage_bytes(db, user.id), "quota_bytes": user.quota_bytes}


@router.post("", status_code=201)
def upload(request: Request, file: UploadFile = File(...), principal: Principal = Depends(current_principal),
           db: Session = Depends(get_db)) -> dict:
    document = documents.receive_upload(db, principal.user, file.file, file.filename or "document.pdf")
    db.commit()
    run("ingest_document", document.id, queue="analysis", priority=P1_VISIBLE)
    db.expire_all()
    return _detail(db, documents.get_owned_document(db, principal.user, document.id))


@router.get("/{document_id}")
def get_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _detail(db, documents.get_owned_document(db, user, document_id))


@router.patch("/{document_id}")
def rename(document_id: str, body: Rename, principal: Principal = Depends(current_principal),
           db: Session = Depends(get_db)) -> dict:
    document = documents.get_owned_document(db, principal.user, document_id)
    name = documents.safe_name(body.name)
    document.name = name if name.lower().endswith(".pdf") else name + ".pdf"
    audit.record(db, "document.rename", principal.user.id, document_id=document.id, name=document.name)
    db.commit()
    return _detail(db, document)


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, principal: Principal = Depends(current_principal),
                    db: Session = Depends(get_db)) -> None:
    document = documents.get_owned_document(db, principal.user, document_id)
    documents.soft_delete(db, document)
    audit.record(db, "document.delete", principal.user.id, document_id=document.id)
    db.commit()


@router.get("/{document_id}/pages")
def list_pages(document_id: str, revision: int | None = None, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> list[dict]:
    document = documents.get_owned_document(db, user, document_id, allow_processing=False)
    return _pages(db, document, documents.revision_row(db, document, revision))


@router.get("/{document_id}/pages/{page_id}/scene")
def page_scene(document_id: str, page_id: str, revision: int | None = None, version: int | None = None,
               diagnostics: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Scene of one page. ``version`` pins an exact (immutable) page version; otherwise the page as
    it is in ``revision`` (default: current)."""
    document = documents.get_owned_document(db, user, document_id, allow_processing=False)
    revision_row = documents.revision_row(db, document, revision)
    index = next((i for i, e in enumerate(revision_row.page_map) if e["page_id"] == page_id), None)
    if version is None:
        if index is None:
            raise NotFound("Page not found in this revision.")
        entry = revision_row.page_map[index]
    else:
        entry = {"page_id": page_id, "version": version}
        index = index if index is not None else 0
    version = documents.page_version(db, document.id, page_id, entry["version"])
    if version.analysis_status != "ready":
        run("analyze_page_version", version.id, queue="analysis", priority=P1_VISIBLE)
        db.refresh(version)
    scene = load_scene(db, version, index)
    if scene is None:
        raise ServiceError("analysis_failed", "This page could not be analysed.", status=500)
    payload = public_scene(scene, page_id, entry["version"], diagnostics)
    payload["revision"] = revision_row.revision
    return payload


@router.post("/{document_id}/analyze", status_code=202)
def prioritise_analysis(document_id: str, body: AnalyzeIn, user: User = Depends(current_user),
                        db: Session = Depends(get_db)) -> dict:
    """Visible/nearby pages jump the background analysis queue (§21, §50)."""
    document = documents.get_owned_document(db, user, document_id, allow_processing=False)
    revision_row = documents.revision_row(db, document)
    wanted = set(body.page_ids)
    priority = {"visible": P1_VISIBLE, "nearby": P2_NEARBY}.get(body.priority, P3_BACKGROUND)
    queued = 0
    for entry in revision_row.page_map:
        if entry["page_id"] not in wanted:
            continue
        version = documents.page_version(db, document.id, entry["page_id"], entry["version"])
        if version.analysis_status == "pending":
            enqueue("analyze_page_version", version.id, queue="analysis", priority=priority)
            queued += 1
    return {"queued": queued}


@router.get("/{document_id}/search")
def search(document_id: str, q: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Unified text search over analysed pages of the current revision (§38)."""
    document = documents.get_owned_document(db, user, document_id, allow_processing=False)
    needle = q.strip().lower()[:200]
    if not needle:
        return {"results": [], "pending_pages": 0}
    revision_row = documents.revision_row(db, document)
    index_of = {(e["page_id"], e["version"]): i for i, e in enumerate(revision_row.page_map)}
    versions = db.scalars(select(PageVersion).where(PageVersion.document_id == document.id)).all()
    wanted = {v.id: index_of[(v.page_id, v.version)] for v in versions if (v.page_id, v.version) in index_of}
    pending = sum(1 for v in versions if v.id in wanted and v.analysis_status != "ready")
    rows = db.execute(
        select(SceneObjectRow.page_version_id, SceneObjectRow.object_id, SceneObjectRow.text)
        .where(SceneObjectRow.page_version_id.in_(list(wanted)), SceneObjectRow.text.is_not(None),
               func.lower(SceneObjectRow.text).contains(needle, autoescape=True))
        .limit(1000)).all()
    page_ids = {v.id: v.page_id for v in versions}
    results = sorted(({"page_index": wanted[r.page_version_id], "page_id": page_ids[r.page_version_id],
                       "object_id": r.object_id, "text": r.text} for r in rows), key=lambda r: r["page_index"])
    return {"results": results, "pending_pages": pending}


@router.get("/{document_id}/revisions")
def revisions(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    document = documents.get_owned_document(db, user, document_id)
    rows = db.scalars(select(DocumentRevision).where(DocumentRevision.document_id == document.id)
                      .order_by(DocumentRevision.revision.desc()).limit(500))
    return [{"revision": r.revision, "parent_revision": r.parent_revision, "kind": r.kind, "size": r.size,
             "sha256": r.sha256, "page_count": len(r.page_map), "created_at": r.created_at,
             "batch_id": r.batch_id, "current": r.revision == document.current_revision} for r in rows]


@router.get("/{document_id}/revisions/{revision}/file")
def revision_file(document_id: str, revision: int, user: User = Depends(current_user),
                  db: Session = Depends(get_db)) -> FileResponse:
    document = documents.get_owned_document(db, user, document_id, allow_processing=False)
    row = documents.revision_row(db, document, revision)
    return FileResponse(get_store().path(row.blob_key), media_type="application/pdf",
                        headers={"Cache-Control": "private, max-age=31536000, immutable",
                                 "ETag": f'"{row.sha256}"', "Content-Disposition": "inline"})


@router.post("/{document_id}/restore/{revision}")
def restore(document_id: str, revision: int, body: RevisionGuard, principal: Principal = Depends(current_principal),
            db: Session = Depends(get_db)) -> dict:
    documents.get_owned_document(db, principal.user, document_id, allow_processing=False)
    return editing.restore(db, principal.user, document_id, revision, body.expected_revision)


@router.post("/{document_id}/operations", status_code=200)
def submit_operations(document_id: str, body: OperationBatchIn, wait: bool = True,
                      principal: Principal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    document = documents.get_owned_document(db, principal.user, document_id, allow_processing=False)
    batch = editing.submit(db, principal.user, document, body.base_revision, body.client_batch_id,
                           [op.model_dump() for op in body.operations])
    if wait and batch.status == BatchStatus.pending:
        batch = editing.commit(db, batch)
    elif not wait:
        enqueue("commit_batch", batch.id, queue="pdf_mutation", priority=0)
    editing.raise_for_failure(batch)
    return _batch_payload(batch)


def _batch_payload(batch: OperationBatch) -> dict:
    return {"accepted": True, "operation_batch_id": batch.id, "status": batch.status.value,
            "optimistic_revision": batch.base_revision + 1, "revision": batch.result_revision,
            "warnings": batch.warnings, "outcome": batch.outcome, "error": batch.error}


@router.get("/{document_id}/operations/{batch_id}")
def batch_status(document_id: str, batch_id: str, user: User = Depends(current_user),
                 db: Session = Depends(get_db)) -> dict:
    document = documents.get_owned_document(db, user, document_id)
    batch = db.get(OperationBatch, batch_id)
    if batch is None or batch.document_id != document.id:
        raise NotFound("Operation not found.")
    return _batch_payload(batch)


@router.post("/{document_id}/undo")
def undo(document_id: str, body: RevisionGuard, principal: Principal = Depends(current_principal),
         db: Session = Depends(get_db)) -> dict:
    documents.get_owned_document(db, principal.user, document_id, allow_processing=False)
    return editing.undo(db, principal.user, document_id, body.expected_revision)


@router.post("/{document_id}/redo")
def redo(document_id: str, body: RevisionGuard, principal: Principal = Depends(current_principal),
         db: Session = Depends(get_db)) -> dict:
    documents.get_owned_document(db, principal.user, document_id, allow_processing=False)
    return editing.redo(db, principal.user, document_id, body.expected_revision)


@router.post("/{document_id}/exports", status_code=202)
def create_export(document_id: str, body: ExportIn, wait: bool = True, principal: Principal = Depends(current_principal),
                  db: Session = Depends(get_db)) -> dict:
    document = documents.get_owned_document(db, principal.user, document_id, allow_processing=False)
    revision = documents.revision_row(db, document, body.revision).revision
    export = Export(document_id=document.id, owner_id=principal.user.id, revision=revision, mode=body.mode)
    db.add(export)
    audit.record(db, "document.export", principal.user.id, document_id=document.id, revision=revision, mode=body.mode)
    db.commit()
    if wait:
        run("export_document", export.id, queue="export", priority=P1_VISIBLE)
    else:
        enqueue("export_document", export.id, queue="export", priority=P1_VISIBLE)
    db.refresh(export)
    return _export_payload(export)


def _export_payload(export: Export) -> dict:
    return {"id": export.id, "status": export.status, "revision": export.revision, "mode": export.mode,
            "size": export.size, "error": export.error, "created_at": export.created_at}


@router.get("/{document_id}/exports/{export_id}")
def get_export(document_id: str, export_id: str, user: User = Depends(current_user),
               db: Session = Depends(get_db)) -> dict:
    document = documents.get_owned_document(db, user, document_id)
    export = db.get(Export, export_id)
    if export is None or export.document_id != document.id:
        raise NotFound("Export not found.")
    return _export_payload(export)


@router.get("/{document_id}/exports/{export_id}/file")
def download_export(document_id: str, export_id: str, user: User = Depends(current_user),
                    db: Session = Depends(get_db)) -> FileResponse:
    document = documents.get_owned_document(db, user, document_id)
    export = db.get(Export, export_id)
    if export is None or export.document_id != document.id or export.status != "ready" or not export.blob_key:
        raise NotFound("Export not found.")
    return FileResponse(get_store().path(export.blob_key), media_type="application/pdf",
                        filename=document.name, headers={"Cache-Control": "private, no-store"})
