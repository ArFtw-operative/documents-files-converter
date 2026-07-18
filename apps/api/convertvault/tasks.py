import mimetypes
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from celery import Task
from sqlalchemy import func, select

from .celery_app import celery
from .config import settings
from .database import SessionLocal
from .engines.base import ConversionContext
from .engines.registry import resolve
from .models import (AuthSession, FileStatus, Job, JobStatus, PdfDocumentVersion,
                     PdfEditProject, PdfEditSession, StoredFile)
from .storage import get_storage


def category_for(mime: str) -> str:
    if mime.startswith("image/"): return "image"
    if mime == "application/pdf": return "pdf"
    if "word" in mime or "document" in mime: return "document"
    if "sheet" in mime or "excel" in mime or "csv" in mime: return "spreadsheet"
    if "presentation" in mime or "powerpoint" in mime: return "presentation"
    return "other"


@celery.task(bind=True, name="convertvault.tasks.run_conversion", autoretry_for=(), acks_late=True)
def run_conversion(self: Task, job_id: str) -> None:
    storage = get_storage()
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job or job.status == JobStatus.cancelled: return
        source_record = db.get(StoredFile, job.input_file_id)
        if not source_record: return
        job.status, job.progress, job.started_at = JobStatus.running, 5, datetime.now(UTC); db.commit()
        try:
            engine, capability = resolve(job.operation, source_record.extension, job.target_format)
            with tempfile.TemporaryDirectory(prefix=f"cv-{job.id}-") as directory:
                root = Path(directory)
                source = root / f"input.{source_record.extension}"
                destination = root / f"output.{job.target_format}"
                storage.copy_to(source_record.storage_key, source)
                additional_sources: list[Path] = []
                # The primary input is also addressable by file ID so page-copy
                # commands can duplicate or move pages within the same PDF.
                additional_file_map: dict[str, str] = {source_record.id: str(source)}
                input_ids = job.options.get("input_file_ids", [])
                for sequence, input_id in enumerate(input_ids):
                    if input_id == source_record.id: continue
                    additional_record = db.get(StoredFile, input_id)
                    if not additional_record or additional_record.owner_id != source_record.owner_id:
                        raise ValueError("An additional input is unavailable")
                    additional_path = root / f"input-{sequence}.{additional_record.extension}"
                    storage.copy_to(additional_record.storage_key, additional_path); additional_sources.append(additional_path)
                    additional_file_map[additional_record.id] = str(additional_path)
                job.progress = 25; job.engine_id = engine.engine_id; db.commit()
                job_options = {**job.options, "_operation": job.operation}
                job_options["_additional_file_map"] = additional_file_map
                if job.operation in {"pdf.encrypt", "pdf.decrypt"}:
                    from .dispatcher import consume_job_secret
                    secret = consume_job_secret(job.id)
                    if not secret: raise ValueError("The temporary PDF password expired; retry the job")
                    job_options["password"] = secret
                context = ConversionContext(source, destination, source_record.extension, job.target_format,
                                            job_options, additional_sources)
                outputs = engine.convert(context)
                if not outputs or not destination.exists() or destination.stat().st_size == 0:
                    raise RuntimeError("The conversion engine produced no valid output")
                validation_report = None
                if job.operation == "pdf.edit":
                    from .engines.pdf_editor import validate_edited_pdf
                    validation_report = validate_edited_pdf(source, destination, job.options.get("operations", []))
                db.refresh(job)
                if job.status == JobStatus.cancelled:
                    return
                job.progress = 80; db.commit()
                key = f"{source_record.owner_id}/derivatives/{job.id}/{destination.name}"
                size, checksum = storage.put_path(key, destination)
                mime = mimetypes.guess_type(destination.name)[0] or "application/octet-stream"
                output_meta = {"job_id": job.id, "engine": engine.engine_id}
                if validation_report:
                    output_meta["validation_report"] = validation_report
                if job.operation == "text.extract":
                    output_meta.update({"extracted_from": source_record.id, "ocr_language": job.options.get("ocr_language"),
                                        "fidelity_note": "Source wording preserved; whitespace and reading order normalized."})
                if job.operation == "pdf.compress":
                    output_meta.update({"original_size": source_record.size, "compressed_size": size,
                                        "reduction_percent": round((1 - size / source_record.size) * 100, 1) if source_record.size else 0})
                output = StoredFile(owner_id=source_record.owner_id, parent_file_id=source_record.id,
                    original_name=destination.name, display_name=f"{Path(source_record.display_name).stem}.{job.target_format}",
                    extension=job.target_format, mime_type=mime, category=category_for(mime), size=size,
                    checksum_sha256=checksum, storage_key=key, meta=output_meta)
                db.add(output); db.flush(); job.output_file_id = output.id
                if job.operation == "pdf.edit" and job.options.get("project_id"):
                    project = db.get(PdfEditProject, job.options["project_id"])
                    if project and project.owner_id == job.owner_id:
                        project.output_file_id = output.id; project.status = "published"
                if job.operation == "pdf.edit" and job.options.get("session_id"):
                    session = db.get(PdfEditSession, job.options["session_id"])
                    if session and session.owner_id == job.owner_id and session.document_id == job.options.get("document_id"):
                        version_number = int(db.scalar(select(func.coalesce(func.max(PdfDocumentVersion.version_number), 0))
                                                       .where(PdfDocumentVersion.document_id == session.document_id)) or 0) + 1
                        db.add(PdfDocumentVersion(document_id=session.document_id, file_id=output.id,
                                                  version_number=version_number, kind="edited",
                                                  validation_report=validation_report or {}, created_by=job.owner_id))
                        session.status = "active"
                job.warning = " ".join(capability.limitations) if capability.approximate else None
                job.status, job.progress, job.finished_at = JobStatus.succeeded, 100, datetime.now(UTC); db.commit()
        except Exception as exc:
            db.rollback(); job = db.get(Job, job_id)
            job.status, job.finished_at = JobStatus.failed, datetime.now(UTC)
            job.error_code = "CONVERSION_FAILED"
            job.error_message = f"The conversion could not be completed: {str(exc)[:300]}. The original file remains safe."
            if job.operation == "pdf.edit" and job.options.get("project_id"):
                project = db.get(PdfEditProject, job.options["project_id"])
                if project and project.owner_id == job.owner_id:
                    project.status = "failed"
            if job.operation == "pdf.edit" and job.options.get("session_id"):
                session = db.get(PdfEditSession, job.options["session_id"])
                if session and session.owner_id == job.owner_id:
                    session.status = "failed"
            db.commit()


@celery.task(name="convertvault.tasks.cleanup_trash")
def cleanup_trash() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=settings.trash_retention_days)
    count, storage = 0, get_storage()
    with SessionLocal() as db:
        records = db.scalars(select(StoredFile).where(StoredFile.status == FileStatus.deleted, StoredFile.deleted_at < cutoff)).all()
        for record in records:
            storage.delete(record.storage_key)
            record.storage_key = f"purged/{record.id}"
            record.size = 0; record.checksum_sha256 = "0" * 64
            record.original_name = record.display_name = "Permanently deleted"
            record.meta = {"purged": True, "purged_at": datetime.now(UTC).isoformat()}; count += 1
        db.commit()
    return count


@celery.task(name="convertvault.tasks.reconcile_stale_jobs")
def reconcile_stale_jobs() -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=max(settings.job_timeout_image, settings.job_timeout_pdf,
                                                        settings.job_timeout_office, settings.job_timeout_general) + 300)
    count = 0
    with SessionLocal() as db:
        jobs = db.scalars(select(Job).where(Job.status == JobStatus.running, Job.started_at < cutoff)).all()
        for job in jobs:
            job.status = JobStatus.failed; job.finished_at = datetime.now(UTC); job.error_code = "WORKER_LOST"
            job.error_message = "The worker stopped reporting this job. The original file remains safe; retrying may help."
            count += 1
        db.commit()
    return count


@celery.task(name="convertvault.tasks.cleanup_sessions")
def cleanup_sessions() -> int:
    with SessionLocal() as db:
        sessions = db.scalars(select(AuthSession).where(AuthSession.expires_at < datetime.now(UTC))).all()
        count = len(sessions)
        for session in sessions: db.delete(session)
        db.commit(); return count
