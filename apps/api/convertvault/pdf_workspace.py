import csv
import io
import re
import tempfile
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

import fitz
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from PIL import Image, ImageChops
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    AuditLog,
    FileStatus,
    Job,
    PdfDocument,
    PdfDocumentVersion,
    PdfEditSession,
    PdfEditorCommand,
    PdfRecoverySnapshot,
    StoredFile,
    User,
)
from .pdf_scene import build_page_scene, interpret_document
from .pdf_compare import compare_pdfs
from .engines.base import ConversionContext
from .engines.pdf_editor import PdfEditorEngine, resolve_font
from .schemas import (PdfAnnotationReplyRequest, PdfAnnotationUpdateRequest, PdfCompareRequest, PdfFormDataImportRequest,
                      PdfCommandCreate, PdfDocumentCreate, PdfEditOperation, PdfHistoryAction,
                      PdfImageObjectEditRequest, PdfNativeTextEditRequest, PdfSessionCreate,
                      PdfPageGeometryRequest, PdfPageImportRequest, PdfVectorObjectEditRequest)
from .security import current_user
from .storage import get_storage, safe_name
from .api import enqueue_job


router = APIRouter(prefix="/api/v1/pdf", tags=["PDF Workspace"])


def _owned_file(file_id: str, user: User, db: Session) -> StoredFile:
    record = db.get(StoredFile, file_id)
    if not record or record.owner_id != user.id or record.status != FileStatus.active:
        raise HTTPException(404, "PDF source file not found")
    if record.extension.lower() != "pdf":
        raise HTTPException(422, "A PDF document is required")
    return record


def _owned_document(document_id: str, user: User, db: Session) -> PdfDocument:
    document = db.get(PdfDocument, document_id)
    if not document or document.owner_id != user.id:
        raise HTTPException(404, "PDF document not found")
    return document


def _owned_session(session_id: str, user: User, db: Session, lock: bool = False) -> PdfEditSession:
    query = select(PdfEditSession).where(PdfEditSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = db.scalar(query)
    if not session or session.owner_id != user.id:
        raise HTTPException(404, "PDF edit session not found")
    return session


def _document_json(document: PdfDocument, db: Session) -> dict:
    versions = db.scalar(select(func.count(PdfDocumentVersion.id)).where(PdfDocumentVersion.document_id == document.id)) or 0
    sessions = db.scalar(select(func.count(PdfEditSession.id)).where(PdfEditSession.document_id == document.id)) or 0
    return {
        "id": document.id,
        "source_file_id": document.source_file_id,
        "name": document.name,
        "status": document.status,
        "version_count": versions,
        "session_count": sessions,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _version_json(version: PdfDocumentVersion) -> dict:
    return {
        "id": version.id,
        "document_id": version.document_id,
        "file_id": version.file_id,
        "version_number": version.version_number,
        "kind": version.kind,
        "validation_report": version.validation_report,
        "created_by": version.created_by,
        "created_at": version.created_at,
    }


def _session_json(session: PdfEditSession) -> dict:
    return {
        "id": session.id,
        "document_id": session.document_id,
        "base_version_id": session.base_version_id,
        "status": session.status,
        "revision": session.revision,
        "cursor": session.cursor,
        "operations": session.operations,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


def _command_json(command: PdfEditorCommand) -> dict:
    return {
        "id": command.id,
        "session_id": command.session_id,
        "sequence": command.sequence,
        "idempotency_key": command.idempotency_key,
        "command": command.command,
        "page": command.page,
        "object_id": command.object_id,
        "payload": command.payload,
        "before_state": command.before_state,
        "after_state": command.after_state,
        "status": command.status,
        "created_by": command.created_by,
        "created_at": command.created_at,
    }


def _next_sequence(session_id: str, db: Session) -> int:
    return int(db.scalar(select(func.coalesce(func.max(PdfEditorCommand.sequence), 0)).where(PdfEditorCommand.session_id == session_id)) or 0) + 1


def _active_operations(session_id: str, db: Session) -> list[dict]:
    commands = db.scalars(
        select(PdfEditorCommand).where(
            PdfEditorCommand.session_id == session_id,
            PdfEditorCommand.status == "applied",
            ~PdfEditorCommand.command.startswith("history."),
        ).order_by(PdfEditorCommand.sequence)
    ).all()
    return [command.payload for command in commands]


def _snapshot_if_due(session: PdfEditSession, db: Session, force: bool = False) -> None:
    if not force and session.revision % 25:
        return
    db.add(PdfRecoverySnapshot(session_id=session.id, revision=session.revision,
                               cursor=session.cursor, operations=session.operations))


def _source_for_session(session: PdfEditSession, user: User, db: Session) -> StoredFile:
    version = db.get(PdfDocumentVersion, session.base_version_id)
    if not version or version.document_id != session.document_id:
        raise HTTPException(409, "The edit session base version is unavailable")
    return _owned_file(version.file_id, user, db)


def _materialize_session(session: PdfEditSession, user: User, db: Session,
                         root: Path, operations: list[dict] | None = None) -> Path:
    resolved = session.operations if operations is None else operations
    source = _source_for_session(session, user, db)
    source_path, edited_path = root / "source.pdf", root / "session.pdf"
    get_storage().copy_to(source.storage_key, source_path)
    assets: dict[str, str] = {}
    for file_id in {file_id for item in resolved
                    for file_id in (item.get("image_file_id"), item.get("source_file_id"),
                                    item.get("attachment_file_id")) if file_id}:
        asset = db.get(StoredFile, file_id)
        if not asset or asset.owner_id != user.id or asset.status != FileStatus.active:
            raise HTTPException(422, "A PDF edit asset is unavailable")
        asset_path = root / f"{asset.id}.{asset.extension}"
        get_storage().copy_to(asset.storage_key, asset_path)
        assets[asset.id] = str(asset_path)
    try:
        PdfEditorEngine().convert(ConversionContext(
            source_path, edited_path, "pdf", "pdf",
            {"operations": resolved, "_additional_file_map": assets},
        ))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - every engine fault must surface as an edit error
        raise HTTPException(422, f"The live PDF workspace could not be materialized: {exc}") from exc
    return edited_path


def _validate_operations(session: PdfEditSession, user: User, db: Session,
                         operations: list[dict]) -> None:
    """Dry-run an operation list through the real engine before it is stored.

    This is the safety gate that keeps a session healthy forever: a command
    that cannot be applied is rejected here with the engine's actionable
    message and never enters the recoverable history.
    """
    with tempfile.TemporaryDirectory(prefix="cv-pdf-validate-") as directory:
        _materialize_session(session, user, db, Path(directory), operations=operations)


def _missing_glyphs(path: Path, font_xref: int | None, font_name: str | None, value: str) -> list[str]:
    if not value:
        return []
    font = None
    try:
        with fitz.open(path) as document:
            if font_xref:
                extracted = document.extract_font(font_xref)
                if len(extracted) >= 4 and extracted[3]:
                    font = fitz.Font(fontbuffer=extracted[3])
        if font is None:
            builtins = {"Helvetica": "helv", "Times-Roman": "tiro", "Courier": "cour"}
            font = fitz.Font(fontname=builtins.get(str(font_name), "helv"))
        return sorted({character for character in value if not character.isspace() and not font.has_glyph(ord(character))})
    except Exception:
        return []


def _find_scene_object(path: Path, session_id: str, object_id: str,
                       expected_type: str) -> tuple[dict, dict]:
    with fitz.open(path) as document:
        page_count = document.page_count
    for page_number in range(1, page_count + 1):
        scene = build_page_scene(path, session_id, page_number)
        match = next((item for item in scene["objects"] if item["id"] == object_id), None)
        if match:
            if match["type"] != expected_type:
                raise HTTPException(422, f"The selected scene object is not a {expected_type.replace('_', ' ')}")
            return match, scene
    raise HTTPException(404, "The selected PDF object no longer exists in this session")


def _overlaps(first: list[float], second: list[float], padding: float = 0) -> bool:
    expanded = fitz.Rect(first)
    expanded.x0 -= padding; expanded.y0 -= padding
    expanded.x1 += padding; expanded.y1 += padding
    return expanded.intersects(fitz.Rect(second))


def _pdf_color(value, fallback: str = "#000000") -> str:
    if not value:
        return fallback
    channels = list(value)
    if len(channels) == 1:
        channels *= 3
    if len(channels) < 3:
        return fallback
    return "#" + "".join(f"{max(0, min(255, round(float(channel) * 255))):02x}" for channel in channels[:3])


def _annotation_state(document: fitz.Document, xref: int) -> str:
    value = document.xref_get_key(xref, "State")[1]
    normalized = value.lstrip("/").lower() if value and value != "null" else "none"
    return {"marked": "open"}.get(normalized, normalized)


def _annotation_records(path: Path) -> list[dict]:
    records: list[dict] = []
    with fitz.open(path) as document:
        for page in document:
            page_annots = list(page.annots() or [])
            names = {(annot.info or {}).get("id") or f"xref:{annot.xref}": annot.xref for annot in page_annots}
            xref_names = {xref: name for name, xref in names.items()}
            for annot in page_annots:
                info = annot.info or {}
                name = info.get("id") or f"xref:{annot.xref}"
                irt_value = document.xref_get_key(annot.xref, "IRT")[1]
                parent_xref = None
                if irt_value and irt_value != "null":
                    try:
                        parent_xref = int(irt_value.split()[0])
                    except (TypeError, ValueError):
                        parent_xref = None
                parent_id = xref_names.get(parent_xref)
                border = annot.border or {}
                colors = annot.colors or {}
                attachment = None
                if annot.type[1] == "FileAttachment":
                    try:
                        attachment = annot.file_info
                    except Exception:
                        attachment = {"available": True}
                records.append({
                    "id": name,
                    "xref": annot.xref,
                    "page": page.number + 1,
                    "type": annot.type[1],
                    "rect": list(annot.rect),
                    "author": info.get("title") or "",
                    "subject": info.get("subject") or "",
                    "comment": info.get("content") or "",
                    "created_at": info.get("creationDate") or "",
                    "modified_at": info.get("modDate") or "",
                    "status": _annotation_state(document, annot.xref),
                    "parent_id": parent_id,
                    "thread_id": parent_id or name,
                    "locked": bool(annot.flags & fitz.PDF_ANNOT_IS_LOCKED),
                    "printable": bool(annot.flags & fitz.PDF_ANNOT_IS_PRINT),
                    "visible": not bool(annot.flags & (fitz.PDF_ANNOT_IS_HIDDEN | fitz.PDF_ANNOT_IS_NO_VIEW)),
                    "opacity": max(0.0, float(annot.opacity)),
                    "color": _pdf_color(colors.get("stroke")),
                    "fill": _pdf_color(colors.get("fill"), "") if colors.get("fill") else None,
                    "width": float(border.get("width") or 1),
                    "border_style": {"S": "solid", "D": "dashed", "B": "beveled", "I": "inset", "U": "underline"}.get(border.get("style"), "solid"),
                    "attachment": attachment,
                })
    counts = {record["id"]: 0 for record in records}
    for record in records:
        if record["parent_id"] in counts:
            counts[record["parent_id"]] += 1
    for record in records:
        record["reply_count"] = counts[record["id"]]
    return records


def _annotation_target(path: Path, annotation_name: str) -> dict:
    match = next((item for item in _annotation_records(path) if item["id"] == annotation_name), None)
    if not match:
        raise HTTPException(404, "The selected annotation no longer exists in this session")
    return match


def _pdf_literal(value: str) -> str | None:
    if not value or value == "null":
        return None
    if value.startswith("(") and value.endswith(")"):
        return value[1:-1].replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return value.lstrip("/")


def _form_records(path: Path) -> tuple[list[dict], list[dict]]:
    fields: list[dict] = []
    errors: list[dict] = []
    with fitz.open(path) as document:
        for page in document:
            for widget in page.widgets() or []:
                pattern = _pdf_literal(document.xref_get_key(widget.xref, "CVValidation")[1])
                value = "" if widget.field_value is None else str(widget.field_value)
                required = bool(widget.field_flags & fitz.PDF_FIELD_IS_REQUIRED)
                field = {
                    "id": f"field:{widget.xref}", "xref": widget.xref, "page": page.number + 1,
                    "name": widget.field_name or "", "label": widget.field_label or "",
                    "type": widget.field_type_string, "value": value,
                    "default_value": _pdf_literal(document.xref_get_key(widget.xref, "DV")[1]),
                    "required": required, "readonly": bool(widget.field_flags & fitz.PDF_FIELD_IS_READ_ONLY),
                    "hidden": widget.field_display == 1, "printable": widget.field_display != 2,
                    "rect": list(widget.rect), "font": widget.text_font, "font_size": widget.text_fontsize,
                    "text_color": widget.text_color, "fill_color": widget.fill_color,
                    "border_color": widget.border_color, "border_width": widget.border_width,
                    "alignment": {0: "left", 1: "center", 2: "right"}.get(widget.text_format, "left"),
                    "format": _pdf_literal(document.xref_get_key(widget.xref, "CVFormat")[1]) or "none",
                    "validation_pattern": pattern,
                    "calculation": _pdf_literal(document.xref_get_key(widget.xref, "CVCalculation")[1]),
                    "export_value": _pdf_literal(document.xref_get_key(widget.xref, "CVExportValue")[1]),
                    "max_length": widget.text_maxlen, "choices": list(widget.choice_values or []),
                    "tab_order": int(document.xref_get_key(widget.xref, "StructParent")[1]) + 1
                    if document.xref_get_key(widget.xref, "StructParent")[0] == "int" else None,
                }
                if required and not value.strip():
                    errors.append({"field": field["name"], "page": field["page"], "code": "required", "message": "A required field is empty"})
                if pattern and value:
                    try:
                        if re.fullmatch(pattern, value) is None:
                            errors.append({"field": field["name"], "page": field["page"], "code": "pattern", "message": "The value does not match the field validation pattern"})
                    except re.error:
                        errors.append({"field": field["name"], "page": field["page"], "code": "invalid_pattern", "message": "The stored validation pattern is invalid"})
                fields.append(field)
    return fields, errors


@router.post("/compare")
def compare_documents(payload: PdfCompareRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    before = _owned_file(payload.before_file_id, user, db)
    after = _owned_file(payload.after_file_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-compare-") as directory:
        root = Path(directory); before_path, after_path = root / "before.pdf", root / "after.pdf"
        get_storage().copy_to(before.storage_key, before_path); get_storage().copy_to(after.storage_key, after_path)
        try:
            report = compare_pdfs(before_path, after_path, payload.model_dump(exclude={"before_file_id", "after_file_id"}))
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, f"The PDFs could not be compared: {exc}") from exc
    report.update({"before_file_id": before.id, "after_file_id": after.id,
                   "before_name": before.display_name, "after_name": after.display_name})
    return report


@router.get("/compare/render")
def render_comparison(before_file_id: str, after_file_id: str,
                      side: str = Query(default="overlay", pattern="^(before|after|overlay)$"),
                      page: int = Query(default=1, ge=1), dpi: int = Query(default=120, ge=36, le=240),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    before = _owned_file(before_file_id, user, db); after = _owned_file(after_file_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-compare-render-") as directory:
        root = Path(directory); paths = {"before": root / "before.pdf", "after": root / "after.pdf"}
        get_storage().copy_to(before.storage_key, paths["before"]); get_storage().copy_to(after.storage_key, paths["after"])
        images = {}
        for key, path in paths.items():
            with fitz.open(path) as document:
                if page > document.page_count:
                    images[key] = Image.new("RGB", (800, 1000), "white")
                else:
                    png = document[page - 1].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False).tobytes("png")
                    images[key] = Image.open(io.BytesIO(png)).convert("RGB")
        if side in images:
            result = images[side]
        else:
            width, height = max(item.width for item in images.values()), max(item.height for item in images.values())
            first, second = Image.new("RGB", (width, height), "white"), Image.new("RGB", (width, height), "white")
            first.paste(images["before"], (0, 0)); second.paste(images["after"], (0, 0))
            result = Image.blend(first, second, 0.5)
            mask = ImageChops.difference(first, second).convert("L").point(lambda value: 150 if value > 18 else 0)
            result.paste(Image.new("RGB", result.size, "#ef4444"), mask=mask)
        stream = io.BytesIO(); result.save(stream, "PNG")
    return Response(stream.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/documents", status_code=201)
def create_document(payload: PdfDocumentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    source = _owned_file(payload.file_id, user, db)
    document = PdfDocument(owner_id=user.id, source_file_id=source.id,
                           name=safe_name(payload.name or Path(source.display_name).stem))
    db.add(document); db.flush()
    version = PdfDocumentVersion(document_id=document.id, file_id=source.id, version_number=1,
                                 kind="source", created_by=user.id,
                                 validation_report={"original_preserved": True, "validated": False})
    db.add(version)
    db.add(AuditLog(actor_id=user.id, action="pdf.document.create", object_type="pdf_document",
                    object_id=document.id, details={"source_file_id": source.id}))
    db.commit(); db.refresh(document)
    return _document_json(document, db)


@router.get("/documents")
def list_documents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(PdfDocument).where(PdfDocument.owner_id == user.id)
                       .order_by(PdfDocument.updated_at.desc()).limit(200)).all()
    return {"items": [_document_json(item, db) for item in items]}


@router.get("/documents/{document_id}")
def get_document(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _document_json(_owned_document(document_id, user, db), db)


@router.get("/documents/{document_id}/versions")
def list_versions(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    document = _owned_document(document_id, user, db)
    items = db.scalars(select(PdfDocumentVersion).where(PdfDocumentVersion.document_id == document.id)
                       .order_by(PdfDocumentVersion.version_number.desc())).all()
    return {"items": [_version_json(item) for item in items]}


@router.get("/documents/{document_id}/model")
def document_model(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    document = _owned_document(document_id, user, db)
    source = _owned_file(document.source_file_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-model-") as directory:
        path = Path(directory) / "source.pdf"
        get_storage().copy_to(source.storage_key, path)
        try:
            return interpret_document(path)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


@router.post("/documents/{document_id}/sessions", status_code=201)
def create_session(document_id: str, payload: PdfSessionCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    document = _owned_document(document_id, user, db)
    if payload.base_version_id:
        version = db.get(PdfDocumentVersion, payload.base_version_id)
        if not version or version.document_id != document.id:
            raise HTTPException(404, "PDF document version not found")
    else:
        version = db.scalar(select(PdfDocumentVersion).where(PdfDocumentVersion.document_id == document.id)
                            .order_by(PdfDocumentVersion.version_number.desc()).limit(1))
    if not version:
        raise HTTPException(409, "This PDF document has no usable version")
    session = PdfEditSession(document_id=document.id, owner_id=user.id, base_version_id=version.id,
                             status="active", revision=0, cursor=0, operations=[])
    db.add(session); db.flush()
    seed_operations = [operation.model_dump(exclude_none=True, exclude_unset=True)
                       for operation in payload.operations]
    if seed_operations:
        _validate_operations(session, user, db, seed_operations)
        for sequence, (operation_model, operation) in enumerate(zip(payload.operations, seed_operations), 1):
            db.add(PdfEditorCommand(
                session_id=session.id, sequence=sequence,
                idempotency_key=f"seed-{sequence}-{uuid.uuid4()}",
                command=operation_model.kind, page=operation_model.page,
                object_id=operation_model.object_id, payload=operation,
                before_state={"revision": sequence - 1, "cursor": sequence - 1},
                after_state={"operation": operation}, status="applied", created_by=user.id,
            ))
        session.operations = seed_operations
        session.cursor = len(seed_operations)
        session.revision = len(seed_operations)
    _snapshot_if_due(session, db, force=True)
    db.add(AuditLog(actor_id=user.id, action="pdf.session.create", object_type="pdf_session",
                    object_id=session.id, details={"document_id": document.id, "base_version_id": version.id}))
    db.commit(); db.refresh(session)
    return _session_json(session)


@router.get("/documents/{document_id}/sessions")
def list_sessions(document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    document = _owned_document(document_id, user, db)
    items = db.scalars(select(PdfEditSession).where(PdfEditSession.document_id == document.id,
                                                    PdfEditSession.owner_id == user.id)
                       .order_by(PdfEditSession.updated_at.desc())).all()
    return {"items": [_session_json(item) for item in items]}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _session_json(_owned_session(session_id, user, db))


@router.get("/sessions/{session_id}/scene")
def session_scene(session_id: str, page: int = Query(1, ge=1), user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-scene-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        try:
            scene = build_page_scene(path, session.id, page)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    scene["revision"] = session.revision
    return scene


@router.get("/sessions/{session_id}/pages/{page_number}/render")
def render_session_page(session_id: str, page_number: int, dpi: int = Query(120, ge=36, le=300),
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-live-preview-") as directory:
        root = Path(directory)
        edited_path = _materialize_session(session, user, db, root)
        try:
            with fitz.open(edited_path) as document:
                if page_number < 1 or page_number > document.page_count:
                    raise HTTPException(404, "The requested preview page does not exist")
                pixmap = document[page_number - 1].get_pixmap(
                    matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False,
                )
                payload = pixmap.tobytes("png")
        except HTTPException:
            raise
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(422, f"The live PDF preview could not be rendered: {exc}") from exc
    return Response(payload, media_type="image/png", headers={
        "Cache-Control": "no-store", "X-PDF-Revision": str(session.revision),
    })


@router.get("/sessions/{session_id}/document")
def inspect_session_document(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-session-inspect-") as directory:
        edited_path = _materialize_session(session, user, db, Path(directory))
        with fitz.open(edited_path) as document:
            pages = []
            for page in document:
                fonts = page.get_fonts(full=True)
                text_blocks = []
                for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT).get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            value = span.get("text", "").strip()
                            if value:
                                text_blocks.append({"text": value, "rect": span.get("bbox"),
                                                    "font": span.get("font"), "size": span.get("size"),
                                                    "color": f"#{int(span.get('color', 0)) & 0xFFFFFF:06x}"})
                            if len(text_blocks) >= 500: break
                        if len(text_blocks) >= 500: break
                    if len(text_blocks) >= 500: break
                pages.append({"page": page.number + 1, "width": page.rect.width, "height": page.rect.height,
                              "rotation": page.rotation, "fonts": sorted({font[3] for font in fonts}),
                              "subset_fonts": sorted({font[3] for font in fonts if "+" in font[3]}),
                              "images": len(page.get_images(full=True)), "links": len(page.get_links()),
                              "annotations": sum(1 for _ in (page.annots() or [])), "text_blocks": text_blocks})
            return {"page_count": document.page_count, "metadata": document.metadata, "pages": pages,
                    "has_signatures": any("Sig" in str(widget.field_type_string)
                                          for page in document for widget in (page.widgets() or [])),
                    "revision": session.revision}


@router.get("/sessions/{session_id}/commands")
def list_commands(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    items = db.scalars(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id)
                       .order_by(PdfEditorCommand.sequence)).all()
    return {"items": [_command_json(item) for item in items], "revision": session.revision,
            "cursor": session.cursor}


@router.patch("/sessions/{session_id}/text/{object_id}")
def edit_native_text(session_id: str, object_id: str, payload: PdfNativeTextEditRequest,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-native-text-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        scenes = []
        with fitz.open(path) as document:
            page_count = document.page_count
        for page_number in range(1, page_count + 1):
            scene = build_page_scene(path, session.id, page_number)
            match = next((item for item in scene["objects"] if item["id"] == object_id), None)
            if match:
                scenes.append(match)
                break
        if not scenes:
            raise HTTPException(404, "The selected text object no longer exists in this session")
        text_object = scenes[0]
        if text_object["type"] != "text_run":
            raise HTTPException(422, "The selected scene object is not native PDF text")
        if text_object["editability"] == "Protected":
            raise HTTPException(422, "This text uses a protected or unsupported font structure and cannot be safely rewritten")
        original = text_object["text"]
        if payload.range.end > len(original):
            raise HTTPException(422, "The selected character range extends beyond the current text object")
        if payload.font_policy == "cancel":
            raise HTTPException(422, "Text editing was cancelled by the requested font policy")
        missing = _missing_glyphs(path, text_object["style"].get("font_xref"),
                                  text_object["style"].get("font"), payload.text)
        effective_font = payload.replacement_font or text_object["style"].get("font") or "Helvetica"
        effective_font_policy = payload.font_policy
        if missing and payload.font_policy == "preserve_or_prompt":
            try:
                resolve_font(effective_font)
                effective_font_policy = "substitute"
            except ValueError:
                shown = " ".join(missing[:12])
                raise HTTPException(422, f"The original font does not contain the required glyphs: {shown}. Install the matching full font family or select it explicitly to continue.")
        if payload.font_policy == "substitute" and not payload.replacement_font:
            raise HTTPException(422, "Select a replacement font before using font substitution")
        operation = PdfEditOperation.model_validate({
            "kind": "content.edit_text_object",
            "page": text_object["page"],
            "object_id": object_id,
            "rect": text_object["bounds"],
            "origin": text_object["transform"][4:6],
            "text": original,
            "replacement": payload.text,
            "range_start": payload.range.start,
            "range_end": payload.range.end,
            "font": effective_font,
            "font_size": text_object["style"].get("font_size") or 12,
            "color": text_object["style"].get("color") or "#000000",
            "font_resource": text_object["style"].get("font_resource"),
            "font_xref": text_object["style"].get("font_xref"),
            "reflow_policy": payload.reflow_policy,
            "font_policy": effective_font_policy,
        })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        object_id=object_id,
    ), user, db)


@router.patch("/sessions/{session_id}/paragraphs/{object_id}")
def edit_native_paragraph(session_id: str, object_id: str, payload: PdfNativeTextEditRequest,
                          user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Replace a complete PDF text block and reflow it inside its page bounds."""
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(
        PdfEditorCommand.session_id == session.id,
        PdfEditorCommand.idempotency_key == payload.idempotency_key,
    ))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session),
                "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-native-paragraph-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        paragraph = None
        with fitz.open(path) as document:
            page_count = document.page_count
        for page_number in range(1, page_count + 1):
            scene = build_page_scene(path, session.id, page_number)
            paragraph = next((item for item in scene["objects"]
                              if item["id"] == object_id and item["type"] == "text_block"), None)
            if paragraph:
                break
        if not paragraph:
            raise HTTPException(404, "The selected paragraph no longer exists in this session")
        if paragraph["editability"] == "Protected":
            raise HTTPException(422, "This paragraph contains protected Type 3 glyphs and cannot be safely rewritten")
        original = paragraph["text"]
        if payload.range.end > len(original):
            raise HTTPException(422, "The selected character range extends beyond the current paragraph")
        if payload.font_policy == "cancel":
            raise HTTPException(422, "Paragraph editing was cancelled by the requested font policy")
        missing = _missing_glyphs(path, paragraph["style"].get("font_xref"),
                                  paragraph["style"].get("font"), payload.text)
        effective_font = payload.replacement_font or paragraph["style"].get("font") or "Helvetica"
        effective_font_policy = payload.font_policy
        if missing and payload.font_policy == "preserve_or_prompt":
            try:
                resolve_font(effective_font)
                effective_font_policy = "substitute"
            except ValueError:
                shown = " ".join(missing[:12])
                raise HTTPException(422, f"The original font does not contain the required glyphs: {shown}. Install the matching full font family or select it explicitly to continue.")
        if payload.font_policy == "substitute" and not payload.replacement_font:
            raise HTTPException(422, "Select a replacement font before using font substitution")
        bounds = paragraph["bounds"]
        operation = PdfEditOperation.model_validate({
            "kind": "content.edit_text_block",
            "page": paragraph["page"],
            "object_id": object_id,
            "rect": bounds,
            "origin": bounds[:2],
            "text": original,
            "replacement": payload.text,
            "range_start": payload.range.start,
            "range_end": payload.range.end,
            "font": effective_font,
            "font_size": paragraph["style"].get("font_size") or 12,
            "color": paragraph["style"].get("color") or "#000000",
            "font_resource": paragraph["style"].get("font_resource"),
            "font_xref": paragraph["style"].get("font_xref"),
            "reflow_policy": payload.reflow_policy,
            "font_policy": effective_font_policy,
        })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision,
        idempotency_key=payload.idempotency_key,
        operation=operation,
        object_id=object_id,
    ), user, db)


@router.patch("/sessions/{session_id}/images/{object_id}")
def edit_image_object(session_id: str, object_id: str, payload: PdfImageObjectEditRequest,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    if payload.image_file_id:
        replacement = db.get(StoredFile, payload.image_file_id)
        if not replacement or replacement.owner_id != user.id or replacement.status != FileStatus.active or replacement.category != "image":
            raise HTTPException(422, "The replacement image is unavailable or is not an image file")
    with tempfile.TemporaryDirectory(prefix="cv-pdf-image-object-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        image, scene = _find_scene_object(path, session.id, object_id, "image")
        if image["lock_state"]:
            raise HTTPException(422, "This image is locked and cannot be edited")
        collisions = [item for item in scene["objects"]
                      if item["type"] == "image" and item["id"] != object_id
                      and _overlaps(image["bounds"], item["bounds"])]
        if collisions:
            raise HTTPException(422, "This image overlaps another image object. Safe isolated reconstruction is unavailable; separate the source objects first.")
        kind = {"transform": "content.transform_image", "replace": "content.replace_image_object",
                "delete": "content.delete_image_object"}[payload.action]
        operation = PdfEditOperation.model_validate({
            "kind": kind, "page": image["page"], "object_id": object_id,
            "rect": payload.rect or image["bounds"], "source_rect": image["bounds"],
            "source_xref": image["source"].get("xref"), "rotation": payload.rotation,
            "source_digest": image["source"].get("digest"),
            "crop": payload.crop, "image_file_id": payload.image_file_id,
        })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation, object_id=object_id,
    ), user, db)


@router.patch("/sessions/{session_id}/vectors/{object_id}")
def edit_vector_object(session_id: str, object_id: str, payload: PdfVectorObjectEditRequest,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-vector-object-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        vector, scene = _find_scene_object(path, session.id, object_id, "vector_path")
        if vector["lock_state"] or vector["editability"] == "Protected":
            raise HTTPException(422, "This vector uses clipping, shadings, or operators that cannot be reconstructed safely")
        width = float(vector["properties"].get("width") or 1)
        collisions = [item for item in scene["objects"]
                      if item["type"] == "vector_path" and item["id"] != object_id
                      and _overlaps(vector["bounds"], item["bounds"], width + 1)]
        if collisions:
            raise HTTPException(422, "This vector overlaps another path. Safe isolated reconstruction is unavailable for this object stack.")
        kind = "content.delete_vector_object" if payload.action == "delete" else "content.transform_vector"
        operation = PdfEditOperation.model_validate({
            "kind": kind, "page": vector["page"], "object_id": object_id,
            "rect": payload.rect or vector["bounds"], "source_rect": vector["bounds"],
            "rotation": payload.rotation, "color": payload.color,
            "fill": payload.fill, "width": payload.width, "opacity": payload.opacity,
            "vector_properties": vector["properties"],
        })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation, object_id=object_id,
    ), user, db)


@router.post("/sessions/{session_id}/pages/import", status_code=201)
def import_pdf_page(session_id: str, payload: PdfPageImportRequest,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    imported_file = _owned_file(payload.source_file_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-page-import-") as directory:
        root = Path(directory)
        imported_path = root / "imported.pdf"
        get_storage().copy_to(imported_file.storage_key, imported_path)
        current_path = _materialize_session(session, user, db, root)
        with fitz.open(imported_path) as imported:
            if imported.needs_pass:
                raise HTTPException(422, "The page source PDF is password-protected")
            if payload.source_page > imported.page_count:
                raise HTTPException(422, "The selected source PDF page does not exist")
            text_sample = imported[payload.source_page - 1].get_text("text").strip()[:500] or None
        with fitz.open(current_path) as current:
            maximum = current.page_count + (1 if payload.action == "insert" else 0)
            if payload.page > maximum:
                raise HTTPException(422, "The destination page position does not exist")
    operation = PdfEditOperation.model_validate({
        "kind": "page.insert_from_pdf" if payload.action == "insert" else "page.replace_from_pdf",
        "page": payload.page, "source_file_id": imported_file.id,
        "source_page": payload.source_page, "text": text_sample,
    })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation,
    ), user, db)


@router.patch("/sessions/{session_id}/pages/{page_number}/geometry")
def edit_page_geometry(session_id: str, page_number: int, payload: PdfPageGeometryRequest,
                       user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-page-geometry-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        with fitz.open(path) as document:
            if page_number < 1 or page_number > document.page_count:
                raise HTTPException(404, "The requested PDF page does not exist")
    operation = PdfEditOperation.model_validate({
        "kind": "page.resize" if payload.action == "resize" else "page.set_boxes",
        "page": page_number, "page_width": payload.width, "page_height": payload.height,
        "resize_mode": payload.resize_mode, "page_boxes": payload.boxes,
    })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation,
    ), user, db)


@router.get("/sessions/{session_id}/annotations")
def list_annotations(session_id: str, page: int | None = Query(default=None, ge=1),
                     author: str | None = None, annotation_type: str | None = Query(default=None, alias="type"),
                     status: str | None = None, search: str | None = None,
                     hide_resolved: bool = False, sort: str = Query(default="page", pattern="^(page|newest|oldest)$"),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-annotations-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        items = _annotation_records(path)
    if page is not None:
        items = [item for item in items if item["page"] == page]
    if author:
        items = [item for item in items if author.casefold() in item["author"].casefold()]
    if annotation_type:
        items = [item for item in items if item["type"].casefold() == annotation_type.casefold()]
    if status:
        items = [item for item in items if item["status"] == status.casefold()]
    if hide_resolved:
        resolved = {"accepted", "rejected", "cancelled", "completed", "closed"}
        items = [item for item in items if item["status"] not in resolved]
    if search:
        needle = search.casefold()
        items = [item for item in items if needle in " ".join(
            (item["author"], item["subject"], item["comment"], item["type"])).casefold()]
    if sort == "newest":
        items.sort(key=lambda item: item["modified_at"] or item["created_at"], reverse=True)
    elif sort == "oldest":
        items.sort(key=lambda item: item["modified_at"] or item["created_at"])
    else:
        items.sort(key=lambda item: (item["page"], item["rect"][1], item["rect"][0]))
    return {"items": items, "total": len(items), "revision": session.revision,
            "audio_supported": hasattr(fitz.Page, "add_sound_annot")}


@router.post("/sessions/{session_id}/annotations", status_code=201)
def create_annotation(session_id: str, payload: PdfCommandCreate,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not payload.operation.kind.startswith("annotate.") or payload.operation.kind in {
        "annotate.update", "annotate.reply", "annotate.delete"
    }:
        raise HTTPException(422, "This endpoint only creates PDF annotations")
    values = payload.operation.model_dump(exclude_none=True)
    values.setdefault("annotation_name", f"annot-{payload.idempotency_key[-100:]}")
    if values.get("attachment_file_id"):
        asset = db.get(StoredFile, values["attachment_file_id"])
        if not asset or asset.owner_id != user.id or asset.status != FileStatus.active:
            raise HTTPException(422, "The annotation attachment is unavailable")
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=PdfEditOperation.model_validate(values), object_id=values["annotation_name"],
    ), user, db)


@router.patch("/sessions/{session_id}/annotations/{annotation_name}")
def update_annotation(session_id: str, annotation_name: str, payload: PdfAnnotationUpdateRequest,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-annotation-update-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        current = _annotation_target(path, annotation_name)
    changes = payload.model_dump(exclude_none=True, exclude={"expected_revision", "idempotency_key"})
    operation = PdfEditOperation.model_validate({
        "kind": "annotate.update", "page": current["page"], "rect": current["rect"],
        "annotation_name": current["id"], "text": current["comment"],
        "author": current["author"], "subject": current["subject"],
        "annotation_status": current["status"] if current["status"] in {
            "none", "accepted", "rejected", "cancelled", "completed", "open", "closed"
        } else "none",
        "color": current["color"], "fill": current["fill"], "width": current["width"],
        "opacity": current["opacity"], "border_style": current["border_style"],
        "locked": current["locked"], "printable": current["printable"],
        "visible": current["visible"], **changes,
    })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation, object_id=current["id"],
    ), user, db)


@router.post("/sessions/{session_id}/annotations/{annotation_name}/replies", status_code=201)
def reply_to_annotation(session_id: str, annotation_name: str, payload: PdfAnnotationReplyRequest,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-annotation-reply-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        parent = _annotation_target(path, annotation_name)
    reply_name = f"reply-{payload.idempotency_key[-100:]}"
    operation = PdfEditOperation.model_validate({
        "kind": "annotate.reply", "page": parent["page"], "rect": parent["rect"],
        "annotation_name": reply_name, "parent_annotation_name": parent["id"],
        "text": payload.text, "author": payload.author, "subject": payload.subject,
    })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation, object_id=reply_name,
    ), user, db)


@router.delete("/sessions/{session_id}/annotations/{annotation_name}")
def delete_annotation(session_id: str, annotation_name: str, payload: PdfHistoryAction,
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-annotation-delete-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        current = _annotation_target(path, annotation_name)
    operation = PdfEditOperation.model_validate({
        "kind": "annotate.delete", "page": current["page"], "annotation_name": current["id"],
    })
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation, object_id=current["id"],
    ), user, db)


@router.get("/sessions/{session_id}/forms")
def inspect_forms(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-forms-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        fields, errors = _form_records(path)
    return {"items": fields, "total": len(fields), "valid": not errors, "errors": errors,
            "revision": session.revision, "javascript_executed": False}


@router.get("/sessions/{session_id}/navigation")
def inspect_navigation(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-navigation-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        with fitz.open(path) as document:
            bookmarks = [{"index": index, "level": item[0], "title": item[1], "page": item[2],
                          "destination": item[3] if len(item) > 3 else None}
                         for index, item in enumerate(document.get_toc(simple=False))]
            attachments = [{"name": name, **document.embfile_info(name)} for name in document.embfile_names()]
    return {"bookmarks": bookmarks, "attachments": attachments, "revision": session.revision}


@router.get("/sessions/{session_id}/attachments/download")
def download_embedded_attachment(session_id: str, name: str, user: User = Depends(current_user),
                                 db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-attachment-download-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        with fitz.open(path) as document:
            if name not in document.embfile_names(): raise HTTPException(404, "Embedded attachment not found")
            payload = document.embfile_get(name); info = document.embfile_info(name)
    filename = safe_name(info.get("ufilename") or info.get("filename") or name)
    return Response(payload, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/sessions/{session_id}/forms/data")
def export_form_data(session_id: str, format: str = Query(default="json", pattern="^(json|csv|xfdf)$"),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    with tempfile.TemporaryDirectory(prefix="cv-pdf-form-export-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        fields, errors = _form_records(path)
    values = {field["name"]: field["value"] for field in fields if field["name"]}
    if format == "json":
        return {"values": values, "valid": not errors, "errors": errors, "revision": session.revision}
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(values)); writer.writeheader(); writer.writerow(values)
        return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=form-data.csv"})
    field_xml = "".join(f'<field name="{escape(name)}"><value>{escape(value)}</value></field>' for name, value in values.items())
    payload = f'<?xml version="1.0" encoding="UTF-8"?><xfdf xmlns="http://ns.adobe.com/xfdf/"><fields>{field_xml}</fields></xfdf>'
    return Response(payload, media_type="application/vnd.adobe.xfdf", headers={"Content-Disposition": "attachment; filename=form-data.xfdf"})


@router.post("/sessions/{session_id}/forms/data")
def import_form_data(session_id: str, payload: PdfFormDataImportRequest,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    with tempfile.TemporaryDirectory(prefix="cv-pdf-form-import-") as directory:
        path = _materialize_session(session, user, db, Path(directory))
        fields, _ = _form_records(path)
    known = {field["name"] for field in fields}
    unknown = sorted(set(payload.values) - known)
    if unknown:
        raise HTTPException(422, f"Unknown form fields: {', '.join(unknown[:10])}")
    operation = PdfEditOperation.model_validate({"kind": "form.import_data", "metadata": payload.values})
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation,
    ), user, db)


@router.post("/sessions/{session_id}/forms/reset")
def reset_form_data(session_id: str, payload: PdfHistoryAction,
                    user: User = Depends(current_user), db: Session = Depends(get_db)):
    operation = PdfEditOperation.model_validate({"kind": "form.reset"})
    return apply_command(session_id, PdfCommandCreate(
        expected_revision=payload.expected_revision, idempotency_key=payload.idempotency_key,
        operation=operation,
    ), user, db)


@router.post("/sessions/{session_id}/commands", status_code=201)
def apply_command(session_id: str, payload: PdfCommandCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db, lock=True)
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.status != "active":
        raise HTTPException(409, "This PDF edit session is not active")
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    operation = payload.operation.model_dump(exclude_none=True, exclude_unset=True)
    candidate_operations = [*session.operations, operation]
    _validate_operations(session, user, db, candidate_operations)
    undone = db.scalars(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                       PdfEditorCommand.status == "undone")).all()
    for command in undone:
        command.status = "superseded"
    command = PdfEditorCommand(
        session_id=session.id, sequence=_next_sequence(session.id, db),
        idempotency_key=payload.idempotency_key, command=payload.operation.kind,
        page=payload.operation.page, object_id=payload.object_id, payload=operation,
        before_state={"revision": session.revision, "cursor": session.cursor},
        after_state={"operation": operation}, status="applied", created_by=user.id,
    )
    db.add(command); db.flush()
    session.revision += 1
    session.operations = _active_operations(session.id, db)
    session.cursor = len(session.operations)
    _snapshot_if_due(session, db)
    db.add(AuditLog(actor_id=user.id, action="pdf.command.apply", object_type="pdf_command",
                    object_id=command.id, details={"session_id": session.id, "command": command.command,
                                                   "page": command.page, "object_id": command.object_id,
                                                   "revision": session.revision}))
    db.commit(); db.refresh(command); db.refresh(session)
    return {"command": _command_json(command), "session": _session_json(session), "idempotent_replay": False}


def _history_action(session: PdfEditSession, payload: PdfHistoryAction, user: User, db: Session, action: str):
    existing = db.scalar(select(PdfEditorCommand).where(PdfEditorCommand.session_id == session.id,
                                                        PdfEditorCommand.idempotency_key == payload.idempotency_key))
    if existing:
        return {"command": _command_json(existing), "session": _session_json(session), "idempotent_replay": True}
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    desired = "applied" if action == "undo" else "undone"
    order = PdfEditorCommand.sequence.desc() if action == "undo" else PdfEditorCommand.sequence.asc()
    target = db.scalar(select(PdfEditorCommand).where(
        PdfEditorCommand.session_id == session.id,
        PdfEditorCommand.status == desired,
        ~PdfEditorCommand.command.startswith("history."),
    ).order_by(order).limit(1))
    if not target:
        raise HTTPException(409, f"There is nothing to {action}")
    before = target.status
    target.status = "undone" if action == "undo" else "applied"
    db.flush()
    candidate_operations = _active_operations(session.id, db)
    _validate_operations(session, user, db, candidate_operations)
    history = PdfEditorCommand(
        session_id=session.id, sequence=_next_sequence(session.id, db),
        idempotency_key=payload.idempotency_key, command=f"history.{action}",
        page=target.page, object_id=target.object_id, payload={"target_command_id": target.id},
        before_state={"target_status": before, "revision": session.revision, "cursor": session.cursor},
        after_state={"target_status": target.status}, status="applied", created_by=user.id,
    )
    db.add(history); db.flush()
    session.revision += 1
    session.operations = _active_operations(session.id, db)
    session.cursor = len(session.operations)
    _snapshot_if_due(session, db)
    db.add(AuditLog(actor_id=user.id, action=f"pdf.command.{action}", object_type="pdf_command",
                    object_id=target.id, details={"session_id": session.id, "history_command_id": history.id,
                                                  "revision": session.revision}))
    db.commit(); db.refresh(history); db.refresh(session)
    return {"command": _command_json(history), "session": _session_json(session), "idempotent_replay": False}


@router.post("/sessions/{session_id}/undo")
def undo_command(session_id: str, payload: PdfHistoryAction, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _history_action(_owned_session(session_id, user, db, lock=True), payload, user, db, "undo")


@router.post("/sessions/{session_id}/redo")
def redo_command(session_id: str, payload: PdfHistoryAction, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _history_action(_owned_session(session_id, user, db, lock=True), payload, user, db, "redo")


@router.get("/sessions/{session_id}/recovery")
def recovery_snapshots(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db)
    items = db.scalars(select(PdfRecoverySnapshot).where(PdfRecoverySnapshot.session_id == session.id)
                       .order_by(PdfRecoverySnapshot.revision.desc()).limit(20)).all()
    return {"items": [{"id": item.id, "revision": item.revision, "cursor": item.cursor,
                       "operations": item.operations, "created_at": item.created_at} for item in items]}


@router.post("/sessions/{session_id}/exports", status_code=202)
def export_session(session_id: str, payload: PdfHistoryAction, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _owned_session(session_id, user, db, lock=True)
    existing_command = db.scalar(select(PdfEditorCommand).where(
        PdfEditorCommand.session_id == session.id,
        PdfEditorCommand.idempotency_key == payload.idempotency_key,
    ))
    if existing_command:
        jobs = db.scalars(select(Job).where(Job.owner_id == user.id).order_by(Job.created_at.desc()).limit(200)).all()
        existing_job = next((job for job in jobs if job.options.get("export_command_id") == existing_command.id), None)
        if existing_job:
            return existing_job
        raise HTTPException(409, "The previous export command exists but its job record is unavailable")
    if session.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "The PDF session changed in another client",
                                  "current_revision": session.revision})
    source = _source_for_session(session, user, db)
    asset_ids = list(dict.fromkeys(file_id for operation in session.operations
                                   for file_id in (operation.get("image_file_id"), operation.get("source_file_id"),
                                                   operation.get("attachment_file_id"))
                                   if file_id))
    for asset_id in asset_ids:
        asset = db.get(StoredFile, asset_id)
        if not asset or asset.owner_id != user.id or asset.status != FileStatus.active:
            raise HTTPException(422, "A PDF session asset is unavailable")
    command = PdfEditorCommand(
        session_id=session.id, sequence=_next_sequence(session.id, db),
        idempotency_key=payload.idempotency_key, command="history.export", page=None,
        payload={"operation_count": len(session.operations)},
        before_state={"revision": session.revision, "status": session.status},
        after_state={"status": "exporting"}, status="applied", created_by=user.id,
    )
    db.add(command); db.flush()
    job = Job(owner_id=user.id, input_file_id=source.id, operation="pdf.edit", target_format="pdf",
              options={"operations": session.operations, "input_file_ids": [source.id, *asset_ids],
                       "session_id": session.id, "document_id": session.document_id,
                       "export_command_id": command.id})
    session.status = "exporting"; session.revision += 1
    db.add(job)
    db.add(AuditLog(actor_id=user.id, action="pdf.session.export", object_type="pdf_session",
                    object_id=session.id, details={"command_id": command.id, "job_id": job.id,
                                                   "revision": session.revision}))
    db.commit(); db.refresh(job)
    try:
        enqueue_job(job, "pdf", db)
    except HTTPException:
        session = db.get(PdfEditSession, session.id)
        session.status = "active"; db.commit()
        raise
    db.refresh(job)
    return job
