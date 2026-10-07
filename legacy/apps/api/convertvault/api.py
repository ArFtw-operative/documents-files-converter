import mimetypes
import asyncio
import hashlib
import json
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from jwt import InvalidTokenError
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal, get_db
from .dispatcher import dispatch_job, store_job_secret
from .engines.registry import capabilities, health, resolve
from .models import AppSetting, AuditLog, AuthSession, FileStatus, Folder, Job, JobStatus, PdfEditProject, PdfEditRevision, Preset, Role, Share, StoredFile, Tag, User
from .schemas import FileOut, FileUpdate, FolderCreate, JobCreate, JobOut, LoginRequest, PdfEditOperation, PdfProjectCreate, PdfProjectUpdate, PresetCreate, RefreshRequest, SetupRequest, ShareCreate, TagCreate, TokenOut, UserCreate, UserOut, UserUpdate
from .security import current_user, hash_password, require_admin, token_pair, verify_password
from .storage import get_storage, safe_name
from .tasks import category_for

router = APIRouter(prefix="/api/v1")


def enqueue_job(job: Job, queue: str, db: Session) -> None:
    try:
        dispatch_job(job.id, queue)
    except Exception as exc:
        job.status = JobStatus.failed
        job.finished_at = datetime.now(UTC)
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message = "No conversion worker could accept this job. Check Redis and the worker services, then retry."
        db.commit()
        raise HTTPException(503, job.error_message) from exc


def issue_session(db: Session, user: User) -> tuple[str, str, AuthSession]:
    session = AuthSession(user_id=user.id, refresh_token_hash=f"pending-{uuid.uuid4()}",
                          expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days))
    db.add(session); db.flush()
    access, refresh = token_pair(user, session.id)
    session.refresh_token_hash = hashlib.sha256(refresh.encode()).hexdigest()
    return access, refresh, session


def login_limit(request: Request, email: str) -> tuple[object | None, str]:
    identity = f"{request.client.host if request.client else 'unknown'}:{email.lower()}"
    key = f"login-attempt:{hashlib.sha256(identity.encode()).hexdigest()}"
    try:
        from redis import Redis
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=0.15, socket_timeout=0.15)
        if int(client.get(key) or 0) >= 5:
            raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes")
        return client, key
    except HTTPException:
        raise
    except Exception:
        return None, key


def disabled_operations(db: Session) -> set[str]:
    setting = db.get(AppSetting, "disabled_capabilities")
    return set(setting.value.get("operations", [])) if setting else set()


@router.get("/setup/status")
def setup_status(db: Session = Depends(get_db)) -> dict:
    custom = db.get(AppSetting, "app_name")
    return {"required": (db.scalar(select(func.count(User.id))) or 0) == 0, "app_name": custom.value.get("value", settings.app_name) if custom else settings.app_name}


@router.post("/setup", response_model=TokenOut, status_code=201)
def setup(payload: SetupRequest, db: Session = Depends(get_db)):
    if (db.scalar(select(func.count(User.id))) or 0) != 0:
        raise HTTPException(409, "Initial setup has already been completed")
    user = User(email=payload.email.lower(), display_name=payload.display_name,
                password_hash=hash_password(payload.password), role=Role.admin, quota_bytes=settings.default_user_quota)
    db.add(user); db.flush(); access, refresh, _ = issue_session(db, user); db.commit(); db.refresh(user)
    return {"access_token": access, "refresh_token": refresh, "user": user}


@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    limiter, limit_key = login_limit(request, payload.email)
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        if limiter:
            try:
                limiter.incr(limit_key); limiter.expire(limit_key, 900)
            except Exception: pass
        time.sleep(0.25)
        raise HTTPException(401, "Email or password is incorrect")
    if limiter:
        try: limiter.delete(limit_key)
        except Exception: pass
    access, refresh, _ = issue_session(db, user)
    db.add(AuditLog(actor_id=user.id, action="auth.login", object_type="user", object_id=user.id)); db.commit()
    return {"access_token": access, "refresh_token": refresh, "user": user}


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    unauthorized = HTTPException(401, "Refresh token is invalid or expired")
    try:
        claims = jwt.decode(payload.refresh_token, settings.secret_key, algorithms=["HS256"])
        if claims.get("type") != "refresh" or not claims.get("sid"): raise unauthorized
    except InvalidTokenError as exc:
        raise unauthorized from exc
    session = db.get(AuthSession, claims["sid"]); token_hash = hashlib.sha256(payload.refresh_token.encode()).hexdigest()
    if not session or session.user_id != claims.get("sub") or session.revoked_at or not secrets.compare_digest(session.refresh_token_hash, token_hash):
        raise unauthorized
    expires = session.expires_at if session.expires_at.tzinfo else session.expires_at.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC): raise unauthorized
    user = db.get(User, session.user_id)
    if not user or not user.is_active: raise unauthorized
    access, refresh_token = token_pair(user, session.id)
    session.refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest(); session.last_used_at = datetime.now(UTC)
    db.commit(); return {"access_token": access, "refresh_token": refresh_token, "user": user}


@router.post("/auth/logout", status_code=204)
def logout(payload: RefreshRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    token_hash = hashlib.sha256(payload.refresh_token.encode()).hexdigest()
    session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.refresh_token_hash == token_hash))
    if session: session.revoked_at = datetime.now(UTC); db.commit()


@router.get("/auth/sessions")
def sessions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(AuthSession).where(AuthSession.user_id == user.id).order_by(AuthSession.created_at.desc())).all()
    return {"items": [{"id": item.id, "created_at": item.created_at, "last_used_at": item.last_used_at,
                       "expires_at": item.expires_at, "revoked": item.revoked_at is not None} for item in items]}


@router.delete("/auth/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = db.get(AuthSession, session_id)
    if not session or session.user_id != user.id: raise HTTPException(404, "Session not found")
    session.revoked_at = datetime.now(UTC); db.commit()


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)): return user


@router.get("/capabilities")
def list_capabilities(user: User = Depends(current_user), db: Session = Depends(get_db)):
    disabled = disabled_operations(db)
    return {"items": [item for item in capabilities() if item["operation"] not in disabled]}


@router.get("/engines")
def list_engines(user: User = Depends(current_user)): return {"items": health()}


@router.post("/files", response_model=FileOut, status_code=201)
def upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    filename = safe_name(file.filename or "upload")
    extension = Path(filename).suffix.lower().lstrip(".") or "bin"
    blocked = {"exe", "dll", "com", "bat", "cmd", "ps1", "sh", "py", "js", "msi", "scr"}
    archives = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"}
    if extension in blocked:
        raise HTTPException(415, "Executable and script uploads are not accepted")
    if extension in archives:
        raise HTTPException(415, "Archives are disabled until safe extraction inspection is enabled")
    header = file.file.read(8); file.file.seek(0)
    if header.startswith((b"MZ", b"\x7fELF")):
        raise HTTPException(415, "The file contents appear executable and were rejected")
    used = db.scalar(select(func.coalesce(func.sum(StoredFile.size), 0)).where(StoredFile.owner_id == user.id, StoredFile.status == FileStatus.active)) or 0
    key = f"{user.id}/originals/{uuid.uuid4()}/{filename}"
    try: size, checksum = get_storage().put(key, file.file)
    except ValueError as exc: raise HTTPException(413, str(exc)) from exc
    if used + size > user.quota_bytes:
        get_storage().delete(key); raise HTTPException(413, "Your storage quota would be exceeded")
    mime = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    duplicate = db.scalar(select(StoredFile).where(StoredFile.owner_id == user.id, StoredFile.checksum_sha256 == checksum,
                                                   StoredFile.status == FileStatus.active).limit(1))
    record = StoredFile(owner_id=user.id, original_name=filename, display_name=filename, extension=extension,
        mime_type=mime, category=category_for(mime), size=size, checksum_sha256=checksum, storage_key=key,
        meta={"duplicate_of": duplicate.id} if duplicate else {})
    db.add(record); db.flush(); db.add(AuditLog(actor_id=user.id, action="file.upload", object_type="file", object_id=record.id)); db.commit(); db.refresh(record)
    return record


@router.get("/files")
def files(search: str = "", category: str | None = None, extensions: str | None = None,
          folder_id: str | None = None, tag_id: str | None = None, favorite: bool | None = None,
          status: FileStatus = FileStatus.active,
          page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
          user: User = Depends(current_user), db: Session = Depends(get_db)):
    criteria = [StoredFile.owner_id == user.id, StoredFile.status == status]
    if search: criteria.append(or_(StoredFile.display_name.ilike(f"%{search}%"), StoredFile.extension.ilike(f"%{search}%")))
    if category: criteria.append(StoredFile.category == category)
    if extensions: criteria.append(StoredFile.extension.in_([item.strip().lower() for item in extensions.split(",") if item.strip()]))
    if folder_id: criteria.append(StoredFile.folder_id == folder_id)
    if favorite is not None: criteria.append(StoredFile.is_favorite == favorite)
    query = select(StoredFile).where(*criteria)
    if tag_id: query = query.join(StoredFile.tags).where(Tag.id == tag_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(StoredFile.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [FileOut.model_validate(item) for item in items], "total": total, "page": page, "page_size": page_size}


def owned_file(file_id: str, user: User, db: Session) -> StoredFile:
    record = db.get(StoredFile, file_id)
    if not record or record.owner_id != user.id: raise HTTPException(404, "File not found")
    return record


@router.get("/files/{file_id}", response_model=FileOut)
def file_detail(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return owned_file(file_id, user, db)


@router.get("/files/{file_id}/download")
def download(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db); stream = get_storage().open(record.storage_key)
    def body():
        try:
            while chunk := stream.read(1024 * 1024): yield chunk
        finally: stream.close()
    return StreamingResponse(body(), media_type=record.mime_type, headers={"Content-Disposition": f'attachment; filename="{safe_name(record.display_name)}"'})


@router.post("/files/{file_id}/trash", response_model=FileOut)
def trash(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db); record.status = FileStatus.deleted; record.deleted_at = datetime.now(UTC); db.commit(); db.refresh(record); return record


@router.post("/files/{file_id}/restore", response_model=FileOut)
def restore(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db); record.status = FileStatus.active; record.deleted_at = None; db.commit(); db.refresh(record); return record


@router.patch("/files/{file_id}", response_model=FileOut)
def update_file(file_id: str, payload: FileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db)
    if payload.folder_id:
        folder = db.get(Folder, payload.folder_id)
        if not folder or folder.owner_id != user.id: raise HTTPException(404, "Folder not found")
    values = payload.model_dump(exclude_unset=True)
    if "display_name" in values: values["display_name"] = safe_name(values["display_name"])
    for key, value in values.items(): setattr(record, key, value)
    db.add(AuditLog(actor_id=user.id, action="file.update", object_type="file", object_id=record.id, details={"fields": list(values)}))
    db.commit(); db.refresh(record); return record


@router.get("/files/{file_id}/versions")
def versions(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db); root = record; visited: set[str] = set()
    while root.parent_file_id and root.id not in visited:
        visited.add(root.id); parent = owned_file(root.parent_file_id, user, db); root = parent
    items = db.scalars(select(StoredFile).where(or_(StoredFile.id == root.id, StoredFile.parent_file_id == root.id)).order_by(StoredFile.created_at)).all()
    return {"root_id": root.id, "items": [FileOut.model_validate(item) for item in items]}


@router.post("/files/{file_id}/favorite", response_model=FileOut)
def favorite(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db); record.is_favorite = not record.is_favorite; db.commit(); db.refresh(record); return record


@router.post("/files/{file_id}/tags/{tag_id}", response_model=FileOut)
def add_file_tag(file_id: str, tag_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db); tag = db.get(Tag, tag_id)
    if not tag or tag.owner_id != user.id: raise HTTPException(404, "Tag not found")
    if tag not in record.tags: record.tags.append(tag)
    db.commit(); db.refresh(record); return record


@router.delete("/files/{file_id}/tags/{tag_id}", response_model=FileOut)
def remove_file_tag(file_id: str, tag_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db); record.tags = [tag for tag in record.tags if tag.id != tag_id]
    db.commit(); db.refresh(record); return record


@router.delete("/files/{file_id}", status_code=204)
def purge(file_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(file_id, user, db)
    if record.status != FileStatus.deleted: raise HTTPException(409, "Move the file to Trash before permanently deleting it")
    get_storage().delete(record.storage_key)
    record.storage_key = f"purged/{record.id}"
    record.size = 0
    record.checksum_sha256 = "0" * 64
    record.meta = {"purged": True}
    record.original_name = "Permanently deleted"
    record.display_name = "Permanently deleted"
    db.commit()


@router.post("/jobs", response_model=JobOut, status_code=202)
def create_job(payload: JobCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(payload.input_file_id, user, db)
    if payload.operation in disabled_operations(db): raise HTTPException(403, "This conversion capability is disabled by the administrator")
    try: resolve(payload.operation, record.extension, payload.target_format)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    input_ids = list(dict.fromkeys([payload.input_file_id, *payload.input_file_ids]))
    if payload.operation == "pdf.merge" and len(input_ids) < 2:
        raise HTTPException(422, "PDF merge requires at least two input files")
    for input_id in input_ids:
        extra = owned_file(input_id, user, db)
        if payload.operation == "pdf.merge" and extra.extension != "pdf":
            raise HTTPException(422, "PDF merge accepts PDF inputs only")
    options = dict(payload.options)
    secret = options.pop("password", None)
    if payload.operation in {"pdf.encrypt", "pdf.decrypt"} and not secret:
        raise HTTPException(422, "A PDF password is required for this operation")
    options["input_file_ids"] = input_ids
    job = Job(owner_id=user.id, input_file_id=record.id, operation=payload.operation,
              target_format=payload.target_format.lower(), options=options)
    db.add(job); db.commit(); db.refresh(job)
    if secret:
        try: store_job_secret(job.id, str(secret), settings.job_timeout_pdf + 300)
        except Exception as exc:
            job.status, job.error_code, job.error_message = JobStatus.failed, "SECRET_STORE_UNAVAILABLE", "The password could not be stored securely for the worker. Retry when Redis is healthy."
            db.commit(); raise HTTPException(503, job.error_message) from exc
    queue = "pdf" if job.operation.startswith("pdf.") else "image" if job.operation.startswith("image.") else "office" if job.operation.startswith("office.") else "general"
    enqueue_job(job, queue, db)
    db.refresh(job)
    return job


@router.get("/jobs")
def jobs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": [JobOut.model_validate(job) for job in db.scalars(select(Job).where(Job.owner_id == user.id).order_by(Job.created_at.desc()).limit(100)).all()]}


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.owner_id != user.id:
        raise HTTPException(404, "Job not found")

    async def events():
        last = None
        for _ in range(900):
            with SessionLocal() as session:
                current = session.get(Job, job_id)
                if current is None:
                    yield "event: error\ndata: {\"detail\":\"Job no longer exists\"}\n\n"
                    return
                state = {"id": current.id, "status": current.status.value, "progress": current.progress,
                         "output_file_id": current.output_file_id, "error_message": current.error_message}
                encoded = json.dumps(state)
                if encoded != last:
                    yield f"event: progress\ndata: {encoded}\n\n"; last = encoded
                if current.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
                    return
            await asyncio.sleep(2)
        yield "event: timeout\ndata: {\"detail\":\"Progress subscription expired\"}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or job.owner_id != user.id: raise HTTPException(404, "Job not found")
    if job.status not in {JobStatus.queued, JobStatus.running}: raise HTTPException(409, "This job can no longer be cancelled")
    job.status, job.finished_at = JobStatus.cancelled, datetime.now(UTC); db.commit(); db.refresh(job); return job


def owned_pdf_project(project_id: str, user: User, db: Session, lock: bool = False) -> PdfEditProject:
    query = select(PdfEditProject).where(PdfEditProject.id == project_id)
    if lock: query = query.with_for_update()
    project = db.scalar(query)
    if not project or project.owner_id != user.id: raise HTTPException(404, "PDF editor project not found")
    return project


def pdf_project_json(project: PdfEditProject) -> dict:
    return {"id": project.id, "source_file_id": project.source_file_id, "output_file_id": project.output_file_id,
            "name": project.name, "operations": project.operations, "revision": project.revision,
            "status": project.status, "created_at": project.created_at, "updated_at": project.updated_at}


@router.post("/pdf/projects", status_code=201)
def create_pdf_project(payload: PdfProjectCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_file(payload.file_id, user, db)
    if record.extension != "pdf": raise HTTPException(422, "The PDF editor accepts PDF source files only")
    project = PdfEditProject(owner_id=user.id, source_file_id=record.id,
                             name=safe_name(payload.name or f"{Path(record.display_name).stem} editing project"), operations=[])
    db.add(project); db.flush(); db.add(PdfEditRevision(project_id=project.id, revision=0, operations=[]))
    db.add(AuditLog(actor_id=user.id, action="pdf_project.create", object_type="pdf_project", object_id=project.id)); db.commit(); db.refresh(project)
    return pdf_project_json(project)


@router.get("/pdf/projects")
def pdf_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(PdfEditProject).where(PdfEditProject.owner_id == user.id).order_by(PdfEditProject.updated_at.desc())).all()
    return {"items": [pdf_project_json(item) for item in items]}


@router.get("/pdf/projects/{project_id}")
def pdf_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return pdf_project_json(owned_pdf_project(project_id, user, db))


@router.put("/pdf/projects/{project_id}")
def update_pdf_project(project_id: str, payload: PdfProjectUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_pdf_project(project_id, user, db, lock=True)
    if project.revision != payload.expected_revision:
        raise HTTPException(409, {"message": "This PDF project changed in another session", "current_revision": project.revision})
    project.revision += 1; project.operations = [operation.model_dump(exclude_none=True) for operation in payload.operations]
    project.status = "draft"; db.add(PdfEditRevision(project_id=project.id, revision=project.revision, operations=project.operations))
    db.commit(); db.refresh(project); return pdf_project_json(project)


@router.get("/pdf/projects/{project_id}/revisions")
def pdf_project_revisions(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_pdf_project(project_id, user, db)
    items = db.scalars(select(PdfEditRevision).where(PdfEditRevision.project_id == project.id).order_by(PdfEditRevision.revision.desc()).limit(100)).all()
    return {"items": [{"revision": item.revision, "operations": item.operations, "created_at": item.created_at} for item in items]}


@router.post("/pdf/projects/{project_id}/restore/{revision}")
def restore_pdf_revision(project_id: str, revision: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_pdf_project(project_id, user, db, lock=True)
    snapshot = db.scalar(select(PdfEditRevision).where(PdfEditRevision.project_id == project.id, PdfEditRevision.revision == revision))
    if not snapshot: raise HTTPException(404, "PDF project revision not found")
    project.revision += 1; project.operations = snapshot.operations; project.status = "draft"
    db.add(PdfEditRevision(project_id=project.id, revision=project.revision, operations=project.operations)); db.commit(); db.refresh(project)
    return pdf_project_json(project)


@router.get("/pdf/projects/{project_id}/document")
def inspect_pdf_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_pdf_project(project_id, user, db); record = owned_file(project.source_file_id, user, db)
    import fitz
    with tempfile.TemporaryDirectory(prefix="cv-pdf-inspect-") as directory:
        source = Path(directory) / "source.pdf"; get_storage().copy_to(record.storage_key, source)
        with fitz.open(source) as document:
            if document.needs_pass: raise HTTPException(422, "This PDF is password-protected")
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
            result = {"page_count": document.page_count, "metadata": document.metadata, "pages": pages,
                      "has_signatures": any("Sig" in str(widget.field_type_string) for page in document for widget in (page.widgets() or []))}
        return result


@router.get("/pdf/projects/{project_id}/pages/{page_number}/render")
def render_pdf_project_page(project_id: str, page_number: int, dpi: int = Query(120, ge=72, le=200),
                            user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_pdf_project(project_id, user, db); record = owned_file(project.source_file_id, user, db)
    import fitz
    with tempfile.TemporaryDirectory(prefix="cv-pdf-render-") as directory:
        source = Path(directory) / "source.pdf"; get_storage().copy_to(record.storage_key, source)
        with fitz.open(source) as document:
            if page_number < 1 or page_number > document.page_count: raise HTTPException(404, "PDF page not found")
            pixmap = document[page_number - 1].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            content = pixmap.tobytes("png")
        return Response(content, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.post("/pdf/projects/{project_id}/publish", response_model=JobOut, status_code=202)
def publish_pdf_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_pdf_project(project_id, user, db)
    if "pdf.edit" in disabled_operations(db): raise HTTPException(403, "PDF editing is disabled by the administrator")
    validated = [PdfEditOperation.model_validate(operation) for operation in project.operations]
    asset_ids = list(dict.fromkeys(file_id for operation in validated
                                   for file_id in (operation.image_file_id, operation.source_file_id,
                                                   operation.attachment_file_id) if file_id))
    for operation in validated:
        if operation.image_file_id and owned_file(operation.image_file_id, user, db).category != "image":
            raise HTTPException(422, "PDF editor image assets must be image files")
        if operation.source_file_id and owned_file(operation.source_file_id, user, db).extension.lower() != "pdf":
            raise HTTPException(422, "Imported page assets must be PDF files")
    job = Job(owner_id=user.id, input_file_id=project.source_file_id, operation="pdf.edit", target_format="pdf",
              options={"operations": [operation.model_dump(exclude_none=True) for operation in validated],
                       "input_file_ids": [project.source_file_id, *asset_ids], "project_id": project.id})
    project.status = "queued"; db.add(job); db.commit(); db.refresh(job); enqueue_job(job, "pdf", db); db.refresh(job)
    return job


@router.delete("/pdf/projects/{project_id}", status_code=204)
def delete_pdf_project(project_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    project = owned_pdf_project(project_id, user, db); db.delete(project); db.commit()


@router.get("/folders")
def folders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": db.scalars(select(Folder).where(Folder.owner_id == user.id).order_by(Folder.name)).all()}


@router.post("/folders", status_code=201)
def create_folder(payload: FolderCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.parent_id:
        parent = db.get(Folder, payload.parent_id)
        if not parent or parent.owner_id != user.id: raise HTTPException(404, "Parent folder not found")
    folder = Folder(owner_id=user.id, parent_id=payload.parent_id, name=payload.name.strip())
    db.add(folder); db.commit(); db.refresh(folder); return folder


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    folder = db.get(Folder, folder_id)
    if not folder or folder.owner_id != user.id: raise HTTPException(404, "Folder not found")
    for record in db.scalars(select(StoredFile).where(StoredFile.folder_id == folder.id)).all(): record.folder_id = None
    db.delete(folder); db.commit()


@router.get("/tags")
def tags(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": db.scalars(select(Tag).where(Tag.owner_id == user.id).order_by(Tag.name)).all()}


@router.post("/tags", status_code=201)
def create_tag(payload: TagCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    existing = db.scalar(select(Tag).where(Tag.owner_id == user.id, func.lower(Tag.name) == payload.name.strip().lower()))
    if existing: raise HTTPException(409, "A tag with this name already exists")
    tag = Tag(owner_id=user.id, name=payload.name.strip(), color=payload.color)
    db.add(tag); db.commit(); db.refresh(tag); return tag


@router.get("/presets")
def presets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": db.scalars(select(Preset).where(Preset.owner_id == user.id).order_by(Preset.name)).all()}


@router.post("/presets", status_code=201)
def create_preset(payload: PresetCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    preset = Preset(owner_id=user.id, **payload.model_dump())
    db.add(preset); db.commit(); db.refresh(preset); return preset


@router.delete("/presets/{preset_id}", status_code=204)
def delete_preset(preset_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    preset = db.get(Preset, preset_id)
    if not preset or preset.owner_id != user.id: raise HTTPException(404, "Preset not found")
    db.delete(preset); db.commit()


@router.post("/files/{file_id}/shares", status_code=201)
def create_share(file_id: str, payload: ShareCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings.enable_public_sharing: raise HTTPException(403, "Public sharing is disabled by the administrator")
    record = owned_file(file_id, user, db)
    if record.status != FileStatus.active: raise HTTPException(409, "Only active files can be shared")
    token = secrets.token_urlsafe(32); token_hash = hashlib.sha256(token.encode()).hexdigest()
    share = Share(file_id=record.id, owner_id=user.id, token_hash=token_hash,
                  expires_at=datetime.now(UTC) + timedelta(hours=payload.expires_in_hours), download_limit=payload.download_limit)
    db.add(share); db.flush(); db.add(AuditLog(actor_id=user.id, action="share.create", object_type="share", object_id=share.id)); db.commit()
    return {"id": share.id, "url": f"{settings.app_url.rstrip('/')}/api/v1/public/shares/{token}", "expires_at": share.expires_at,
            "download_limit": share.download_limit}


@router.get("/shares")
def list_shares(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(Share).where(Share.owner_id == user.id).order_by(Share.created_at.desc())).all()
    return {"items": [{"id": item.id, "file_id": item.file_id, "expires_at": item.expires_at, "download_limit": item.download_limit,
                       "download_count": item.download_count, "is_active": item.is_active} for item in items]}


@router.delete("/shares/{share_id}", status_code=204)
def revoke_share(share_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    share = db.get(Share, share_id)
    if not share or share.owner_id != user.id: raise HTTPException(404, "Share not found")
    share.is_active = False; db.commit()


@router.get("/public/shares/{token}")
def public_share(token: str, db: Session = Depends(get_db)):
    if not settings.enable_public_sharing: raise HTTPException(404, "Share not found")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    share = db.scalar(select(Share).where(Share.token_hash == token_hash))
    if not share or not share.is_active: raise HTTPException(404, "Share not found")
    expires = share.expires_at if share.expires_at.tzinfo else share.expires_at.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC): raise HTTPException(410, "This share has expired")
    if share.download_limit is not None and share.download_count >= share.download_limit: raise HTTPException(410, "This share reached its download limit")
    record = db.get(StoredFile, share.file_id)
    if not record or record.status != FileStatus.active: raise HTTPException(404, "Shared file not found")
    share.download_count += 1; db.commit(); stream = get_storage().open(record.storage_key)
    def body():
        try:
            while chunk := stream.read(1024 * 1024): yield chunk
        finally: stream.close()
    return StreamingResponse(body(), media_type=record.mime_type,
                             headers={"Content-Disposition": f'attachment; filename="{safe_name(record.display_name)}"', "Cache-Control": "private, no-store"})


@router.get("/admin/users")
def admin_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"items": [UserOut.model_validate(item) for item in db.scalars(select(User).order_by(User.created_at)).all()]}


@router.post("/admin/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    user = User(email=payload.email.lower(), display_name=payload.display_name, password_hash=hash_password(payload.password),
                role=Role(payload.role), quota_bytes=settings.default_user_quota)
    db.add(user); db.flush(); db.add(AuditLog(actor_id=admin.id, action="user.create", object_type="user", object_id=user.id)); db.commit(); db.refresh(user); return user


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target: raise HTTPException(404, "User not found")
    values = payload.model_dump(exclude_unset=True)
    if target.id == admin.id and values.get("is_active") is False: raise HTTPException(409, "You cannot deactivate your current administrator account")
    if target.id == admin.id and values.get("role") == "user": raise HTTPException(409, "You cannot remove your own administrator role")
    if "role" in values: values["role"] = Role(values["role"])
    for key, value in values.items(): setattr(target, key, value)
    db.add(AuditLog(actor_id=admin.id, action="user.update", object_type="user", object_id=target.id, details={"fields": list(values)}))
    db.commit(); db.refresh(target); return target


@router.get("/admin/stats")
def admin_stats(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return {"users": db.scalar(select(func.count(User.id))) or 0, "files": db.scalar(select(func.count(StoredFile.id))) or 0,
            "storage_bytes": db.scalar(select(func.coalesce(func.sum(StoredFile.size), 0))) or 0,
            "active_jobs": db.scalar(select(func.count(Job.id)).where(Job.status.in_([JobStatus.queued, JobStatus.running]))) or 0}


@router.get("/admin/audit")
def admin_audit(page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=500),
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    total = db.scalar(select(func.count(AuditLog.id))) or 0
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [{"id": item.id, "actor_id": item.actor_id, "action": item.action, "object_type": item.object_type,
                       "object_id": item.object_id, "details": item.details, "created_at": item.created_at} for item in items],
            "total": total, "page": page, "page_size": page_size}


@router.put("/admin/settings/app-name")
def set_app_name(value: str = Query(min_length=1, max_length=80), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    setting = db.get(AppSetting, "app_name") or AppSetting(key="app_name", value={})
    setting.value = {"value": value.strip()}; db.add(setting)
    db.add(AuditLog(actor_id=admin.id, action="settings.app_name", object_type="setting", object_id="app_name")); db.commit()
    return {"app_name": value.strip()}


@router.get("/admin/capabilities")
def admin_capabilities(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    disabled = disabled_operations(db)
    return {"items": [{**item, "enabled": item["operation"] not in disabled} for item in capabilities()]}


@router.put("/admin/capabilities/{operation}")
def set_capability(operation: str, enabled: bool, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    known = {item["operation"] for item in capabilities()}
    if operation not in known: raise HTTPException(404, "Capability not found")
    disabled = disabled_operations(db)
    if enabled: disabled.discard(operation)
    else: disabled.add(operation)
    setting = db.get(AppSetting, "disabled_capabilities") or AppSetting(key="disabled_capabilities", value={})
    setting.value = {"operations": sorted(disabled)}; db.add(setting)
    db.add(AuditLog(actor_id=admin.id, action="capability.enable" if enabled else "capability.disable",
                    object_type="capability", object_id=operation)); db.commit()
    return {"operation": operation, "enabled": enabled}


@router.get("/admin/fonts")
def fonts(admin: User = Depends(require_admin)):
    if not shutil.which("fc-list"): return {"available": False, "families": [], "files": [], "scanned_at": datetime.now(UTC)}
    result = subprocess.run(["fc-list", "--format", "%{family}\t%{file}\n"], capture_output=True, text=True, timeout=20, check=True)
    rows = [line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line]
    return {"available": True, "families": sorted({family.split(",")[0] for family, _ in rows}),
            "files": sorted({Path(path).name for _, path in rows}), "scanned_at": datetime.now(UTC)}
