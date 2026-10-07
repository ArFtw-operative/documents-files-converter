"""Document-engine tasks. Run in the sandboxed CPU worker in production (no outbound network,
read-only root FS) or inline in dev/test. These are the only server code paths that open PDFs."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pymupdf as fitz
from sqlalchemy import select, update

from pdf_core.analyzer import analyze_page
from pdf_core.geometry import PageSpace
from pdf_core.inspect import inspect_pdf
from pdf_core.mutation import MutationError, apply_batch
from pdf_core.reconcile import reconcile
from pdf_core.validation import qpdf_check, validate_revision

from .config import get_settings
from .db import SessionLocal
from .models import (
    BatchStatus,
    Document,
    DocumentOperation,
    DocumentRevision,
    DocumentStatus,
    Export,
    OperationBatch,
    Page,
    PageVersion,
)
from .services import audit, events
from .services.locks import document_lock, page_version_lock
from .services.scenes import load_scene, store_scene
from .services.storage import get_store
from .worker import celery

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- ingest / analysis


@celery.task(name="folio.tasks.ingest_document")
def ingest_document(document_id: str) -> dict:
    settings = get_settings()
    store = get_store()
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None or document.status != DocumentStatus.processing:
            return {"status": "skipped"}
        try:
            info = inspect_pdf(store.path(document.original_blob_key))
        except Exception as exc:  # noqa: BLE001 - malformed input is expected
            log.info("ingest failed for %s: %s", document_id, exc)
            info = None
        error = None
        if info is None:
            error = "This file could not be read as a PDF."
        elif info["encrypted"]:
            error = "This PDF is password protected. Remove the password and upload it again."
        elif info["page_count"] < 1:
            error = "This PDF has no pages."
        elif info["page_count"] > settings.max_pages:
            error = f"This PDF has more than {settings.max_pages} pages."
        if error:
            document.status, document.error = DocumentStatus.failed, error
            db.commit()
            events.publish(document_id, "document.failed", message=error)
            return {"status": "failed", "error": error}
        page_map = []
        first_version_id = None
        for _ in range(info["page_count"]):
            page = Page(document_id=document.id)
            db.add(page)
            db.flush()
            version = PageVersion(page_id=page.id, document_id=document.id, version=1)
            db.add(version)
            db.flush()
            first_version_id = first_version_id or version.id
            page_map.append({"page_id": page.id, "version": 1})
        blob_key = document.original_blob_key
        db.add(DocumentRevision(document_id=document.id, revision=1, parent_revision=None, blob_key=blob_key,
                                sha256=document.original_sha256, size=document.size, page_map=page_map,
                                kind="original", created_by=document.owner_id,
                                validation={"qpdf": qpdf_check(store.path(blob_key))[0]}))
        document.current_revision = 1
        document.page_count = info["page_count"]
        document.info = info
        document.status = DocumentStatus.ready
        audit.record(db, "document.upload", document.owner_id, document_id=document.id,
                     name=document.name, pages=info["page_count"], size=document.size)
        db.commit()
    analyze_page_version.run(first_version_id)
    events.publish(document_id, "document.analysis.started", revision=1)
    from .services.engine_runner import P3_BACKGROUND, enqueue

    enqueue("analyze_document", document_id, queue="analysis", priority=P3_BACKGROUND)
    return {"status": "ready"}


def _locate(db, version: PageVersion) -> tuple[DocumentRevision, int] | None:
    """Find a revision whose page map contains this page version, and the page's index there."""
    revisions = db.scalars(select(DocumentRevision).where(DocumentRevision.document_id == version.document_id)
                           .order_by(DocumentRevision.revision.desc())).all()
    for revision in revisions:
        for index, entry in enumerate(revision.page_map):
            if entry["page_id"] == version.page_id and entry["version"] == version.version:
                return revision, index
    return None


@celery.task(name="folio.tasks.analyze_page_version")
def analyze_page_version(version_id: str) -> dict:
    store = get_store()
    with SessionLocal() as db:
        with page_version_lock(db, version_id) as version:
            if version is None:
                return {"status": "missing"}
            if version.analysis_status == "ready":
                return {"status": "ready"}
            located = _locate(db, version)
            if located is None:
                return {"status": "orphaned"}
            revision, index = located
            started = time.perf_counter()
            try:
                with fitz.open(store.path(revision.blob_key)) as pdf:
                    scene = analyze_page(pdf, index, version.page_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("analysis failed for %s: %s", version_id, exc)
                version.analysis_status = "failed"
                db.commit()
                return {"status": "failed"}
            previous = None
            if version.parent_version is not None:
                parent = db.scalar(select(PageVersion).where(PageVersion.page_id == version.page_id,
                                                             PageVersion.version == version.parent_version))
                if parent is not None:
                    previous = load_scene(db, parent, index)
            scene = reconcile(previous, scene, version.edited_hints or None)
            store_scene(db, version, scene)
            db.commit()
            elapsed = round((time.perf_counter() - started) * 1000)
    events.publish(revision.document_id, "page.scene.updated", page_id=version.page_id, version=version.version,
                   object_count=len(scene.objects), analysis_ms=elapsed)
    return {"status": "ready"}


@celery.task(name="folio.tasks.analyze_document")
def analyze_document(document_id: str) -> dict:
    """Background analysis of every page in the current revision (P3; visible pages go first via
    explicit P1 requests from the API)."""
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None or document.status != DocumentStatus.ready:
            return {"status": "skipped"}
        revision = db.scalar(select(DocumentRevision).where(DocumentRevision.document_id == document_id,
                                                            DocumentRevision.revision == document.current_revision))
        pending = []
        for entry in revision.page_map:
            version = db.scalar(select(PageVersion).where(PageVersion.page_id == entry["page_id"],
                                                          PageVersion.version == entry["version"]))
            if version is not None and version.analysis_status == "pending":
                pending.append(version.id)
    for version_id in pending:
        analyze_page_version.run(version_id)
    events.publish(document_id, "document.analysis.completed", pages=len(pending))
    return {"status": "ready", "analyzed": len(pending)}


# --------------------------------------------------------------------------- mutation pipeline


def _fail(db, batch: OperationBatch, error: dict) -> dict:
    batch.status = BatchStatus.failed
    batch.error = error
    db.commit()
    events.publish(batch.document_id, "operation.failed", batch_id=batch.id, error=error)
    return {"status": "failed", "error": error}


def _scene_at(db, document_id: str, entry: dict, index: int):
    version = db.scalar(select(PageVersion).where(PageVersion.page_id == entry["page_id"],
                                                  PageVersion.version == entry["version"],
                                                  PageVersion.document_id == document_id))
    if version is None:
        return None
    if version.analysis_status != "ready":
        analyze_page_version.run(version.id)
        db.expire(version)
    return load_scene(db, version, index)


@celery.task(name="folio.tasks.commit_batch")
def commit_batch(batch_id: str) -> dict:
    """Canonical mutation sequence (§89B.4): load last valid revision → apply → write temp →
    reopen/qpdf/visual validation → hash → atomic move → DB commit → publish."""
    store = get_store()
    started = time.perf_counter()
    with SessionLocal() as db:
        batch = db.get(OperationBatch, batch_id)
        if batch is None or batch.status != BatchStatus.pending:
            return {"status": batch.status.value if batch else "missing"}
        with document_lock(db, batch.document_id) as document:
            current = db.scalar(select(DocumentRevision).where(
                DocumentRevision.document_id == document.id, DocumentRevision.revision == document.current_revision))
            operations = db.scalars(select(DocumentOperation).where(DocumentOperation.batch_id == batch.id)
                                    .order_by(DocumentOperation.sequence)).all()
            index_of = {entry["page_id"]: i for i, entry in enumerate(current.page_map)}
            structural = any(op.operation_type in ("rotate_page", "delete_page", "reorder_page", "insert_page")
                             for op in operations)
            if batch.base_revision != document.current_revision and structural:
                return _fail(db, batch, {"code": "target_modified", "message": "The pages changed since this "
                                         "edit was made.", "details": {"current_revision": document.current_revision}})
            scenes: dict[int, object] = {}
            engine_ops = []
            for op in operations:
                index = index_of.get(op.page_id) if op.page_id else None
                if op.page_id and index is None:
                    return _fail(db, batch, {"code": "target_modified", "message": "The page no longer exists.",
                                             "details": {"current_revision": document.current_revision}})
                engine_ops.append({"type": op.operation_type, "page_index": index, "target_ids": op.target_ids,
                                   "payload": op.payload})
                if index is not None and op.operation_type in ("replace_text", "delete_object") and index not in scenes:
                    scenes[index] = _scene_at(db, document.id, current.page_map[index], index)
            temp = store.temp_path()
            source = store.path(current.blob_key)
            try:
                result = apply_batch(source, temp, engine_ops, lambda i: scenes[i],
                                     allow_signed=any(op.payload.get("confirm_invalidate_signature")
                                                      for op in operations))
            except MutationError as exc:
                temp.unlink(missing_ok=True)
                error = exc.as_dict()
                if error["code"] == "target_modified":
                    error["details"]["current_revision"] = document.current_revision
                return _fail(db, batch, error)
            except Exception as exc:  # noqa: BLE001
                log.exception("mutation failed for batch %s", batch_id)
                temp.unlink(missing_ok=True)
                return _fail(db, batch, {"code": "engine_error", "message": "The edit could not be applied.",
                                         "details": {"diagnostic_id": batch_id, "reason": type(exc).__name__}})
            regions = result.regions
            changed_for_validation = {}
            for new_index, src in enumerate(result.page_order):
                if src is not None and src in regions and src not in result.rotated_pages:
                    changed_for_validation[new_index] = (src, regions[src])
            report = validate_revision(source, temp, len(result.page_order), changed_for_validation)
            if report.ok:
                report = _sanity_check(temp, result, report)
            if not report.ok:
                store.keep_failed(temp, f"{batch_id}.pdf")
                return _fail(db, batch, {"code": "validation_failed", "message": "The edited PDF did not pass "
                                         "validation, so the last good version was kept.",
                                         "details": {"diagnostic_id": batch_id, "errors": report.errors}})
            blob = store.adopt(db, document.owner_id, temp)
            new_map = _next_page_map(db, document.id, current.page_map, result)
            new_revision = document.current_revision + 1
            db.add(DocumentRevision(document_id=document.id, revision=new_revision,
                                    parent_revision=document.current_revision, blob_key=blob.key, sha256=blob.sha256,
                                    size=blob.size, page_map=new_map, kind="edit", batch_id=batch.id,
                                    validation=report.as_dict(), created_by=batch.created_by))
            # A new edit makes undone batches unredoable.
            db.execute(update(OperationBatch).where(OperationBatch.document_id == document.id,
                                                    OperationBatch.undone.is_(True),
                                                    OperationBatch.discarded.is_(False))
                       .values(discarded=True))
            batch.status = BatchStatus.committed
            batch.source_revision = document.current_revision
            batch.result_revision = new_revision
            batch.committed_at = datetime.now(UTC)
            batch.warnings = result.warnings
            batch.outcome = {"outcomes": [{"page_id": current.page_map[o.page_index]["page_id"],
                                           "object_id": o.object_id, "kind": o.kind, "new_text": o.new_text,
                                           "new_bbox": o.new_bbox, "fit": o.fit, "warnings": o.warnings,
                                           "substitutions": o.substitutions} for o in result.outcomes],
                             "elapsed_ms": round((time.perf_counter() - started) * 1000)}
            for op in operations:
                op.revision = new_revision
                details = {"page_id": op.page_id, "targets": op.target_ids, "revision_before": new_revision - 1,
                           "revision_after": new_revision}
                if op.operation_type == "replace_text":
                    details.update(old_text=op.payload.get("old_text"), new_text=op.payload.get("new_text"))
                audit.record(db, f"document.{op.operation_type}", batch.created_by, document_id=document.id,
                             batch_id=batch.id, **details)
            previous_revision = document.current_revision
            document.current_revision = new_revision
            document.page_count = len(new_map)
            document.size = blob.size
            db.commit()
            changed_versions = [entry for entry, src in zip(new_map, result.page_order, strict=True)
                                if src is None or src in result.changed_pages]
    # Analyse edited pages right away so the editor gets fresh geometry with the commit event.
    with SessionLocal() as db:
        for entry in changed_versions:
            version = db.scalar(select(PageVersion).where(PageVersion.page_id == entry["page_id"],
                                                          PageVersion.version == entry["version"]))
            if version is not None:
                analyze_page_version.run(version.id)
    events.publish(batch.document_id, "operation.committed", batch_id=batch.id, revision=new_revision,
                   previous_revision=previous_revision, warnings=result.warnings)
    events.publish(batch.document_id, "revision.created", revision=new_revision, kind="edit")
    return {"status": "committed", "revision": new_revision, "warnings": result.warnings}


def _sanity_check(path: Path, result, report):
    """§43.5: every replaced/added text must be present as real text where it was written."""
    with fitz.open(path) as pdf:
        for outcome in result.outcomes:
            if outcome.kind not in ("replace_text", "add_text") or not outcome.new_text or not outcome.new_text.strip():
                continue
            new_index = result.page_order.index(outcome.page_index)
            page = pdf[new_index]
            rotation = page.rotation
            if rotation:
                page.set_rotation(0)
            try:
                rect = PageSpace(page).pdf_rect_to_mupdf(outcome.new_bbox) + (-2, -2, 2, 2)
                found = page.get_textbox(rect)
            finally:
                if rotation:
                    page.set_rotation(rotation)
            if "".join(outcome.new_text.split()) not in "".join(found.split()):
                report.ok = False
                report.errors.append(f"scene_sanity: edited text not found on page {new_index}")
    return report


def _next_page_map(db, document_id: str, old_map: list[dict], result) -> list[dict]:
    new_map = []
    hints_by_page: dict[int, dict] = {}
    for outcome in result.outcomes:
        if outcome.object_id and outcome.kind == "replace_text":
            hints_by_page.setdefault(outcome.page_index, {})[outcome.object_id] = {
                "text": outcome.new_text, "bbox": outcome.new_bbox}
    for src in result.page_order:
        if src is None:
            page = Page(document_id=document_id)
            db.add(page)
            db.flush()
            db.add(PageVersion(page_id=page.id, document_id=document_id, version=1))
            new_map.append({"page_id": page.id, "version": 1})
            continue
        entry = old_map[src]
        if src not in result.changed_pages:
            new_map.append(dict(entry))
            continue
        latest = db.scalar(select(PageVersion.version).where(PageVersion.page_id == entry["page_id"])
                           .order_by(PageVersion.version.desc()).limit(1)) or entry["version"]
        version = PageVersion(page_id=entry["page_id"], document_id=document_id, version=latest + 1,
                              parent_version=entry["version"], edited_hints=hints_by_page.get(src, {}))
        db.add(version)
        db.flush()
        new_map.append({"page_id": entry["page_id"], "version": version.version})
    return new_map


# --------------------------------------------------------------------------- export / maintenance


@celery.task(name="folio.tasks.export_document")
def export_document(export_id: str) -> dict:
    store = get_store()
    with SessionLocal() as db:
        export = db.get(Export, export_id)
        if export is None or export.status != "pending":
            return {"status": "skipped"}
        revision = db.scalar(select(DocumentRevision).where(DocumentRevision.document_id == export.document_id,
                                                            DocumentRevision.revision == export.revision))
        source = store.path(revision.blob_key)
        temp = store.temp_path()
        try:
            with fitz.open(source) as pdf:
                expected = pdf.page_count
                if export.mode == "optimized":
                    pdf.subset_fonts()
                    pdf.save(temp, garbage=4, deflate=True, clean=True, use_objstms=True)
                else:
                    pdf.save(temp, garbage=1, deflate=True)
            report = validate_revision(source, temp, expected, {})
        except Exception as exc:  # noqa: BLE001
            temp.unlink(missing_ok=True)
            export.status, export.error = "failed", f"Export failed ({type(exc).__name__})."
            db.commit()
            events.publish(export.document_id, "export.failed", export_id=export.id)
            return {"status": "failed"}
        if not report.ok:
            store.keep_failed(temp, f"export-{export_id}.pdf")
            export.status, export.error, export.validation = "failed", "The export did not pass validation.", report.as_dict()
            db.commit()
            events.publish(export.document_id, "export.failed", export_id=export.id)
            return {"status": "failed"}
        blob = store.adopt(db, export.owner_id, temp)
        export.blob_key, export.size, export.validation = blob.key, blob.size, report.as_dict()
        export.status, export.finished_at = "ready", datetime.now(UTC)
        db.commit()
    events.publish(export.document_id, "export.completed", export_id=export_id)
    return {"status": "ready"}


@celery.task(name="folio.tasks.maintenance")
def maintenance() -> dict:
    """Startup/hourly reconciliation (§89B.5): drop abandoned temp files, fail stuck batches."""
    store = get_store()
    cutoff = time.time() - 6 * 3600
    removed = 0
    for path in (store.root / "temp").iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    with SessionLocal() as db:
        stale = datetime.now(UTC) - timedelta(minutes=30)
        db.execute(update(OperationBatch).where(OperationBatch.status == BatchStatus.pending,
                                                OperationBatch.created_at < stale)
                   .values(status=BatchStatus.failed, error={"code": "expired", "message": "The edit timed out."}))
        db.commit()
    return {"temp_removed": removed}

