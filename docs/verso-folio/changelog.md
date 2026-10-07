# Verso Folio — Work Log

A chronological record of what was done and why. Design rationale lives in
[decisions.md](decisions.md), scope and status in [roadmap.md](roadmap.md), and running the
system in [operations.md](operations.md).

## 2026-10-07 — Milestone 1: foundation and native vertical slice

### Planning
1. Moved the plan from `\\192.168.68.104\shared` (served from `/srv/shared` on this host) to
   `docs/ConvertVault_PDF_Studio_Flagship_Architecture.md`, verifying the checksum before deleting
   the original.
2. Reviewed the whole plan and the host:
   - The RTX 3050's NVIDIA driver was not loaded on kernel 7.0.0-38, so Ollama ran on CPU.
   - The name *Verso* was already used by the notes app (`verso.local`).
   - ConvertVault was live at `documents-converter.local`.
3. Clarified four decisions with the owner and recorded them as D1–D6 in `decisions.md`:
   - PaddleOCR plus an Ollama assist.
   - Cloud AI enabled by an admin, with user confirmation per request.
   - Separate accounts only.
   - Replace ConvertVault and serve at `folio.local`.
4. Moved the ConvertVault code to `legacy/` (`git mv`, so history is kept). Its running containers
   were unaffected.

### Document engine (`services/pdf_core`)
5. Wrote the scene-graph contract and the single coordinate module (PDF user space).
6. Wrote the native analyzer:
   - logical runs, glyph quads, alignment inference;
   - images, vector clusters, annotations and links;
   - page classification.
7. Wrote the font resolver: embedded subsets are reused by rebuilding their Unicode cmap with
   fontTools, then same-family installed fonts are tried, then fontconfig fallback per character.
8. Wrote text replacement:
   - preserve-box fitting (free space, then tracking, then horizontal scale, then size, then confirmation);
   - right/centre anchoring;
   - support for rotated text, crop boxes and rotated pages;
   - add/delete text and page operations.
9. Every revision is validated: reopen, qpdf, a pixel-drift check outside the edit, and an
   edited-text sanity check. Object identity is reconciled across versions.
10. Bugs found by tests and fixed:
    - `TextWriter` placed text wrongly with a crop-box offset.
    - The rotation sign in `morph` was wrong.
    - Leftover space glyphs remained after a replacement.
    - Re-embedded fonts got renamed.
    - Overlapping runs were interleaved.

### API (`apps/api/folio`)
11. Accounts:
    - cookie sessions with CSRF protection, Argon2 passwords, TOTP, lockout;
    - admin user management, quotas, an audit log;
    - one ownership gate, so a foreign document id returns 404.
12. Data model:
    - documents, stable pages, page versions, revisions, idempotent operation batches;
    - content-addressed storage with atomic writes.
13. Commit pipeline in the worker. Undo, redo and restore copy an earlier revision exactly. Also added
    exports, search, prioritised analysis and a WebSocket event channel.
14. Replaced Pydantic `EmailStr` with a check that accepts LAN domains such as `.local`.

### Editor (`apps/web`, `packages/`)
15. Vite + React + PDF.js editor:
    - virtualised pages and R-tree hit testing;
    - click-to-edit with caret placement;
    - preview in the document's own embedded font, a background mask, an optimistic preview until the canonical render;
    - thumbnails with page operations, contextual properties, history/restore;
    - find, Ctrl+K, keyboard shortcuts, a diagnostics toggle;
    - IndexedDB crash recovery.
16. Fixed an edit-commit bug under React StrictMode, found by the Playwright browser test.

### Deployment
17. Added the Alembic initial migration. The full suite passes on both SQLite and PostgreSQL.
18. Compose stack `folio-*`. The CPU worker has no outbound network, a read-only root, all capabilities
    dropped, and memory and PID limits. Fixes made while deploying:
    - the Caddy file capability under `cap_drop: ALL`;
    - the Alembic path;
    - volume ownership.
19. Ran the browser vertical slice over HTTPS against production, then reset the production volumes
    so no test account remained.
20. Added `enable-folio-local.sh` for the root-only steps (the shared Caddyfile is root-owned) and a
    tested `backup.sh`. The owner ran the enable script: `folio.local` is live and
    `folio-mdns.service` is active.

### Follow-up from first real use
21. Real invoice (`CourierNew,Bold`, not embedded): an edit showed a false "font does not contain"
    warning and embedded a look-alike. Fixes:
    - edits now reuse the page's own non-embedded font resource (WinAnsi simple fonts), so they render like their neighbours and keep exact colours;
    - the "font does not contain" warning only appears when a different typeface is actually used;
    - added the `not_embedded` reason;
    - moved the fontconfig cache to tmpfs.

    Verified by replaying the owner's edit on a copy of the document. 26 backend tests pass.
