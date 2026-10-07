# Verso Folio — Product Decisions (Addendum to Architecture 2.0)

**Status:** Accepted, 2026-10-07
**Base specification:** [ConvertVault PDF Studio Flagship Architecture](../ConvertVault_PDF_Studio_Flagship_Architecture.md)

Verso Folio is the product name for the ConvertVault PDF Studio flagship rebuild. The architecture
document remains authoritative except where this addendum explicitly overrides it.

## D1 — Name and deployment

- Product: **Verso Folio**. Python package `folio`, containers `folio-*`, Compose project `folio`.
- Served at `https://folio.local` through the existing host Caddy (`reverse-proxy`, network
  `atlas-proxy`). LAN-only like other internal apps.
- Verso Folio replaces the running ConvertVault stack. ConvertVault stays up until Folio is verified
  and its data has been migrated, then it is retired.
- Must not collide with the unrelated *Verso* notes app (`verso-*` containers, `verso.local`).
- Completely browser-based. No desktop application.

## D2 — Multi-user: separate accounts (overrides §44.5 "future multi-user")

- Multiple local accounts with Argon2 passwords and optional TOTP MFA.
- Roles: `admin` (manages users, AI providers, system settings) and `user`.
- **Strict per-user isolation:** every document, revision, asset, job, export and AI request is
  owned by exactly one user. Users never see each other's documents. There is no sharing or ACL
  model in this release. Admins manage accounts but have no document browsing UI.
- Ownership is enforced in a single repository layer (`folio.services.documents.get_owned_document`),
  never ad hoc in routes. Cross-user access returns `404`, not `403`, to avoid disclosing existence.
- First-run setup creates the first admin. Afterwards, accounts are created by an admin (self
  registration is off by default and can be enabled in settings).
- Per-user storage quota; audit log records the acting user for every mutation (§45).

## D3 — OCR: PaddleOCR primary, Ollama assist (amends §7.3, §81 Decision 3)

- PaddleOCR remains the single printed-text **detection and geometry** engine because in-place
  editing needs precise token polygons.
- The local **Ollama** vision model (default `gemma4:e2b`) is an *assist* stage, never a second
  voting OCR engine for normal tokens. It is used for:
  - re-reading low-confidence regions (below the configurable review threshold),
  - handwriting reads as a complement to TrOCR,
  - printed/handwriting/stamp/barcode region classification hints,
  - optional semantic invoice fields (§67), always linked back to scene object IDs.
- Ollama results are stored as suggestions with provenance (`engine=ollama`, model, digest) and
  are only applied when confidence rules or the user accept them.
- **GPU arbitration:** the RTX 3050 has 4 GB VRAM and `gemma4:e2b` alone is about 4.3 GB. A single
  GPU model manager owns admission: Paddle/TrOCR load in the GPU worker, and before an Ollama
  vision call the manager unloads them; Ollama is asked to unload (`keep_alive: 0`) before Paddle
  reloads. Visible-page OCR keeps priority (§21).

## D4 — AI providers: local default, cloud opt-in with per-use consent (amends §88)

- Provider registry: `ollama` (local, default), `anthropic` (Claude), `openai` (GPT/Codex models).
- Cloud providers are **disabled by default**. Only an admin can add API keys (encrypted at rest
  with a key derived from `SECRET_KEY`) and enable a provider and its allowed models.
- **Every** request that would send document content to a cloud provider requires an explicit
  user confirmation in the UI that names the provider and describes what will be sent (for example
  "page 2 image + 14 text regions"). Consent is per request, recorded in the audit log, and the API
  rejects cloud calls without a matching single-use consent token.
- Document workers keep no outbound network (§44.2). AI calls go through a dedicated
  `folio-ai-gateway` component that is the only service allowed outbound internet access, and only
  when a cloud provider is enabled.
- AI features are layered on top of the scene graph and operation model: suggestions become normal
  operations the user reviews; AI never mutates PDFs directly.

## D5 — Stack alignment with existing code

The architecture's stack (§7) is applied: Vite + React (replacing the Next.js prototype), Valkey
(replacing Redis), and local content-addressed storage (replacing MinIO). The ConvertVault
conversion features (image/office/Pandoc) are ported into Folio as a later "Convert" module and are
not part of the editor core.

## D6 — Sequencing

Follows §78 and §82: native vertical slice first; OCR/Ollama after native direct editing is
reliable; cloud AI after that. Progress is tracked in [roadmap.md](roadmap.md).
