from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from . import __version__
from .api import router
from .pdf_workspace import router as pdf_workspace_router
from .config import settings
from .database import Base, engine
from .database import SessionLocal
from .dispatcher import dispatch_job
from .models import Job, JobStatus
from sqlalchemy import select

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env != "production":
        Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)
    if settings.app_env == "development":
        with SessionLocal() as db:
            stranded = db.scalars(select(Job).where(Job.status == JobStatus.queued).order_by(Job.created_at)).all()
            for job in stranded:
                queue = "pdf" if job.operation.startswith("pdf.") else "image" if job.operation.startswith("image.") else "office" if job.operation.startswith("office.") else "general"
                dispatch_job(job.id, queue)
    yield


app = FastAPI(title=settings.app_name, version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
                   allow_headers=["Authorization", "Content-Type"])
app.include_router(router)
app.include_router(pdf_workspace_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}
