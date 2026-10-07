# Verso Folio — Roadmap and Status

Sequencing follows architecture §78 and §82–83, with the decisions in [decisions.md](decisions.md).
Step-by-step history: [changelog.md](changelog.md).

## Milestone 1 — Foundation + native vertical slice ✅ (2026-10-07)

Covers Phase 0, Phase 1 and Phase 2, plus parts of Phase 3 and Phase 8.

| Area | Delivered |
|---|---|
| Accounts (D2) | Cookie sessions + CSRF, Argon2, TOTP two-step sign-in, lockout, admin user management, quotas, strict per-user isolation, audit log with privacy mode |
| Document model | Documents, stable pages, page versions, revisions, operation batches (idempotent), content-addressed storage with atomic writes |
| Native analysis | PyMuPDF scene graph: logical runs (baseline clustering, style splits, fake-bold merge, synthetic spaces), glyph quads, alignment inference, images, vector clusters, annotations, links, page classification |
| In-place editing | `replace_text` keeps the embedded font (subset cmap rebuilt), reuses non-embedded font resources (e.g. `CourierNew,Bold`), same-family fallback, per-glyph substitution with warning, preserve-box fitting (free space → tracking ±5% → scale ≥90% → size ≥90% → confirm), right/centre anchoring, rotated text, crop boxes, rotated pages; `add_text`, `delete_object` |
| Pages | Rotate, delete, reorder, insert blank |
| Integrity | Every revision: reopen, qpdf, render-diff outside the edited region, edited-text sanity check; failures keep the last good revision and store the artifact for diagnostics |
| Undo/redo | Exact restoration by revision copy (byte-identical PDF, same object ids); restore any revision |
| Editor UI | Vite/React/PDF.js, collapsed shell, thumbnails, contextual properties, floating toolbar, click-to-edit with caret placement, preview in the document's own font, optimistic preview, fit confirmation, find, Ctrl+K, shortcuts, diagnostics toggle, IndexedDB crash recovery, WebSocket events |
| Deployment | Compose stack (`folio-*`), sandboxed CPU worker (no network, read-only, no capabilities), Alembic, backup script; live at `https://folio.local` |
| Tests | 26 backend tests (SQLite and PostgreSQL), 7 coordinate-engine tests, Playwright browser vertical slice (dev and production stacks) |

## Milestone 2 — Font fidelity, images, annotations (Phase 3 remainder + V1 scope)

- HarfBuzz shaping and kerning for replacement runs; bidi/RTL and Devanagari (§65)
- Wrap bare CFF/Type1 subsets as OpenType so they can be reused like TrueType subsets
- Rename re-embedded system fonts to the document's font name; subset fonts on save
- Formatting changes from the Properties panel (size, colour, bold, italic), reflow block mode (§14.2)
- Image move/resize/replace/crop, annotations and threaded comments (§39), real redaction (§37)
- Visual regression golden suite with stored diff maps (§71)

## Milestone 3 — Scans and photos with GPU OCR + Ollama assist (Phases 4–5, D3)

Needs the NVIDIA driver loaded on the host (see [operations](operations.md#gpu)).

- `folio-worker-gpu` with one model manager: PaddleOCR (detection + recognition), demand-loaded,
  coordinating VRAM with Ollama (`keep_alive: 0` handoff)
- OpenCV preprocessing: boundary, perspective, deskew, illumination (§15.2)
- OCR scene objects with confidence policy; Ollama re-reads low-confidence regions as suggestions
- Raster reconstruction: background fill, table-line preservation, replacement compositing, searchable text layer
- OCR review mode (§59) and OCR cache (§60)

## Milestone 4 — Cloud AI providers with consent (D4)

- Provider registry (Ollama default, Anthropic, OpenAI), admin keys encrypted at rest
- `folio-ai-gateway` as the only service with outbound internet
- Per-request consent tokens naming the provider and the content sent; audit entries
- Features as reviewable operations: rewrite selection, invoice fields (§67), summaries

## Milestone 5 — Tables, ink and hardening (Phases 6–8)

Table structure and cell navigation, ink and handwriting (TrOCR + Ink Style Profile), Prometheus
metrics (§48), large-document performance, and migrating ConvertVault's conversion features into
a Convert module.
