# Verso Folio

A private, self-hosted, browser-based PDF studio where the page itself is the editor. Click
visible text, type, and save a real PDF that keeps the original font, size, colour and alignment.
Several people can use it; each has a separate account and sees only their own documents.

- **Specification:** [Flagship architecture](docs/ConvertVault_PDF_Studio_Flagship_Architecture.md) + [Verso Folio decisions](docs/verso-folio/decisions.md)
- **Status and next milestones:** [roadmap](docs/verso-folio/roadmap.md)
- **Running it:** [operations](docs/verso-folio/operations.md)

## Layout

```text
apps/api/folio/        FastAPI app: routes, models, services, security, Celery tasks
services/pdf_core/     Document engine (PyMuPDF): analyzer, fonts, mutation, validation
apps/web/              Vite + React editor (PDF.js rendering, scene overlay, inline editing)
packages/              coordinate-engine (all PDF↔screen math), scene-schema (shared types)
infra/                 Dockerfiles, Compose stack, deployment scripts
tests/                 golden PDFs, engine + API tests, Playwright browser slice
legacy/                The previous ConvertVault code, kept for reference and porting
```

## Development

```sh
# Backend tests (inside the API image: qpdf, fonts and pinned dependencies)
docker build --target dev -t folio-api-dev -f infra/docker/api.Dockerfile .
docker run --rm -v "$PWD":/app -w /app folio-api-dev python -m pytest -q

# API on :8000 (SQLite, engine inline) and editor on :5173
docker run --rm -p 127.0.0.1:8000:8000 -v "$PWD":/app -w /app folio-api-dev \
  uvicorn folio.main:app --host 0.0.0.0 --port 8000 --reload
npm install && npm run dev

npm test && npm run typecheck && npm run build
```

Licensed under AGPL-3.0-only (see `LICENSE`); third-party components keep their own licences.
