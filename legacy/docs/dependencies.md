# Dependency and license inventory

| Component | Purpose | License family | Included |
|---|---|---|---|
| FastAPI, Pydantic, SQLAlchemy, Celery | API, validation, ORM, queue | MIT/BSD | API/worker |
| PostgreSQL, Redis | metadata, queue/state | PostgreSQL/RSAL-compatible Redis 7.4 distribution terms | Compose |
| MinIO | object storage | AGPLv3 | Compose |
| Pillow, pillow-heif/libheif | image/HEIF conversion | HPND/BSD/LGPL components | worker |
| PyMuPDF, pypdf | PDF rendering/manipulation | AGPLv3/BSD | worker |
| LibreOffice | Office conversion | MPL/LGPL | worker |
| Pandoc | markup conversion | GPLv2+ | worker |
| Tesseract, qpdf, Ghostscript | OCR/PDF tooling | Apache-2.0/Apache-2.0/AGPLv3 | worker |
| Next.js, React | web UI | MIT | web |

Versions are pinned in requirements, package lock, Dockerfiles, and Compose. Operators redistributing images must review complete transitive license notices. Generate an SBOM with `docker sbom IMAGE` or Syft in CI; container/source licenses remain independent of ConvertVault's license.

