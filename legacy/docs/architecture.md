# Architecture

The browser talks only to `web` and `api`. FastAPI authenticates requests, owns metadata and authorization decisions, streams file bytes to the configured storage provider, and submits heavy work to Redis. Dedicated Celery consumers handle `image`, `pdf`, `office`, and `general` queues. The scheduler handles retention. Workers copy input objects into a per-job temporary directory, resolve an installed engine through the capability registry, validate the produced file, store it as a new object, link it to its parent, and remove the temporary directory.

## Data model

- `users`: identity, role, account state, and quota.
- `files`: owner, optional folder/parent derivative, names, MIME/category, byte size, checksum, storage key, state, metadata, and timestamps.
- `jobs`: input/output relationship, operation, engine, target, options, status/progress, warnings, safe error, and timing.
- `folders`: owner-scoped hierarchy.
- `presets`: reusable owner-scoped conversion configuration.
- `audit_logs`: actor, action, object, details, and timestamp.

Indexes cover user and file creation time, active state, extension/category, checksums, job status and creation time, and audit actor/time. Large binaries never enter PostgreSQL.

## Engine matrix

| Adapter | Queue | Main sources | Main targets | Detection |
|---|---|---|---|---|
| Pillow + pillow-heif | image | common raster, HEIC/HEIF | JPEG, PNG, WebP, TIFF, BMP, GIF, PDF | Python import |
| PyMuPDF + pypdf | pdf | PDF | PNG/JPEG/WebP, text, PDF | Python import |
| LibreOffice | office | word-processing, sheets, presentations | supported Office/PDF formats | `soffice` binary |
| Pandoc | general | Markdown, HTML, text, DOCX, EPUB | HTML, DOCX, ODT, RTF, text, EPUB, PDF, Markdown | `pandoc` binary |

The registry is the source of truth. The UI never hard-codes that a binary-dependent conversion exists.

## Repository

`apps/web` is the Next.js UI; `apps/api/convertvault` contains API/domain/storage code; `engines` contains independent adapters; `workers` contains the hardened worker image; `migrations`, `tests`, `scripts`, `infrastructure`, and `docs` contain their corresponding operational assets.

