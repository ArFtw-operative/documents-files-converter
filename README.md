# ConvertVault

ConvertVault is a private, self-hosted file conversion service and document library. It combines a Next.js interface, FastAPI, PostgreSQL metadata, Redis/Celery workers, and either MinIO or local file storage. Conversion capability is detected from the engines actually installed; unsupported pairs are rejected before a job enters a queue.

## What works

- First-run administrator setup, Argon2 password hashing, signed access/refresh tokens, and owner-scoped file access.
- Streamed multi-file uploads and downloads, filename sanitization, quota enforcement, SHA-256 checksums, search, Trash, restore, and derivative lineage.
- Durable queue-separated jobs, real database progress, cancellation checkpoints, job history, useful safe errors, and authenticated server-sent progress events.
- Pillow/pillow-heif image conversion (JPEG, PNG, WebP, GIF, TIFF, BMP, ICO, HEIC/HEIF where available), resize, rotation, metadata controls, transparency backgrounds, and quality settings.
- PDF Studio with persistent non-destructive projects, optimistic revision history, authenticated page previews, page reordering/deletion/insertion/rotation/cropping, existing-text inspection and replacement, new text and graphics, freehand drawing, true redaction, annotations, links, form fields, images, visual signatures, watermarks, headers/footers, metadata, and validated background export.
- A broader PDF suite for merge/split, page extraction, rendering, image extraction, compression presets, metadata removal, AES-256 encryption/decryption, page numbering, form/annotation flattening, structural repair, active-content sanitization, and OCR when OCRmyPDF is installed.
- Local structured text extraction from PDF, DOCX, ODT, RTF, text/Markdown/HTML, CSV/TSV/XLSX, PPTX, EPUB, and common image formats. It preserves source wording, normalizes reading order and paragraph whitespace, and uses Tesseract OCR where needed.
- Capability-detected LibreOffice office conversions and Pandoc markup conversions inside workers with isolated temporary directories and timeouts.
- PostgreSQL, Redis, MinIO, API, four worker queues, scheduler, web UI, migrations, and Caddy reverse proxy in Docker Compose.
- Local-storage development mode, backup/restore scripts, API docs, unit/security/engine tests, and an end-to-end backend conversion test.

## Start with Docker Compose

1. Copy `.env.example` to `.env`.
2. Replace `SECRET_KEY`, `POSTGRES_PASSWORD`, and `S3_SECRET_KEY` with independent random values. For a public hostname, set `APP_DOMAIN` and `APP_URL`.
3. Start the platform:

```sh
docker compose up -d --build
docker compose ps
docker compose logs -f api worker-image
```

Open `http://localhost` and create the initial administrator. OpenAPI is served at `http://localhost/api/docs`. MinIO and PostgreSQL are not published to the host.

To update or stop:

```sh
docker compose pull
docker compose up -d --build
docker compose down
```

## Local development

The supported full environment is Compose. For a lightweight local API, create a Python 3.12 virtual environment, install `apps/api/requirements.txt`, leave the default SQLite/local-storage configuration, and run:

```sh
uvicorn convertvault.main:app --app-dir apps/api --reload
```

Run the web app from `apps/web` with `npm install` and `npm run dev`. Redis is required for API-submitted conversion jobs; tests execute conversion tasks synchronously.

## Verification

```sh
.venv/Scripts/python -m pytest -q   # Windows
npm --prefix apps/web run build
docker compose config --quiet
```

This checkout passed 25 Python tests—including a complete authenticated PDF Studio export flow—and a Next.js production build. Docker was unavailable on the development host, so Compose startup still needs verification on a Docker host. See [architecture](docs/architecture.md), [security](docs/security.md), [supported formats](docs/supported-formats.md), [administration](docs/administrator-guide.md), and [limitations](docs/known-limitations.md).

## Resource starting point

For a small trusted team: 4 CPU cores, 8 GB RAM, and 20 GB plus expected file storage. Give OCR/office workers at least 2 GB each and keep their concurrency at 1. Production sizing depends heavily on page count, image dimensions, and OCR volume.

Licensed under AGPL-3.0-only. Third-party tools retain their own licenses; see [dependency inventory](docs/dependencies.md).
