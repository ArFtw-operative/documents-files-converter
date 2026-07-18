# Enterprise PDF Workspace completion audit

This audit uses the 3,138-line enterprise specification supplied on 18 July 2026 as the acceptance authority. A green unit test or a visible toolbar is not sufficient evidence for a broad requirement. Status values are `implemented`, `partial`, `missing`, or `unverified`.

## Non-negotiable acceptance gate

| # | Requirement | Current evidence | Status |
|---|---|---|---|
| 1 | Select and genuinely edit existing PDF text | Session-stable scene objects expose per-character Unicode, origins, bounds, font resources, and editability. Range edits remove underlying operators, reconstruct native searchable text at the original baseline/style, and validate the result. Type 3/protected runs are explicitly refused. | implemented |
| 2 | Add native text anywhere | PyMuPDF inserts native page text and save/reopen tests extract it | implemented |
| 3 | Separate editing and annotation | Operation kinds and UI tools are distinct | implemented |
| 4 | Select/move/resize/replace/rotate/crop existing images | Stable image objects can be moved, resized, arbitrarily rotated, cropped, replaced, or deleted through recoverable commands and live preview. Ambiguous overlapping image stacks are refused to prevent collateral damage. Mask/soft-mask fidelity corpus remains incomplete. | partial |
| 5 | Inspect and modify vector objects | Existing simple line/curve/quad/rectangle paths are exposed with stable IDs and can be moved, resized, rotated, restyled, or deleted. Clipped, shaded, unsupported, or overlapping paths are protected with a clear explanation. | partial |
| 6 | Complete page operations | Reorder, blank insert, delete, rotate, crop, native insert/replace from another PDF (including links, annotations, and widgets), resize with fit/fill/stretch content transforms, and media/crop/bleed/trim/art boxes are implemented. Visual thumbnail drag/drop and cross-document move remain. | partial |
| 7 | Real persistent annotations | The required native PDF matrix is implemented for highlight, underline, squiggly, strikeout, text note, text box, callout, freehand, line, arrow, rectangle, ellipse, polygon, polyline, stamp, attachment, caret, replace-text, redaction mark, and calibrated line measurement. Stable names, author/subject/comment, colours, opacity, border, status, replies, lock/print/visibility, filtering, sorting, and deletion persist through validated exports. Audio is explicitly unavailable in the installed engine; XFDF/import-export and multi-user collaboration remain. | partial |
| 8 | Secure redaction | Region, keyword-list, email, phone, account, credit-card, national-ID, IP, date, name, and custom-regex redaction remove underlying text and touched image pixels. Selected-page batching, custom appearance, hidden-text and JavaScript scrub, optional metadata/XMP, comments/replies, attachments, and form-value removal are implemented. Export validation records a redaction report and confirms requested keywords/custom patterns are no longer extractable. OCR-specific targeting, repeated-header detection, and a hostile alternate-stream corpus remain. | partial |
| 9 | Complete forms workflow | Native text, multiline, checkbox, radio, combo, list, push button, unsigned signature, date, and numeric fields can be created and configured. Values, defaults, required/read-only/hidden/print, appearance, alignment, safe validation metadata, calculation metadata, export values, maximum length, comb/multiline/password/no-scroll flags, and tab order persist. JSON/CSV/XFDF export, bulk import, reset, validation, and selected/all flattening are implemented without executing document JavaScript. Automatic detection/alignment/duplication UI, FDF import, and barcode support remain. | partial |
| 10 | Create and validate digital signatures | Visual signature image only; PKCS#12 signing and validation absent | missing |
| 11 | Searchable and editable OCR | Whole-document OCR/searchable output exists when binaries are installed; region OCR, confidence review, and editable reconstruction are absent | partial |
| 12 | Undo and redo across editing tools | Persisted authoritative undo/redo works across text, image, vector, page, annotation, form, and content commands; branching supersedes abandoned redo commands and is covered by API/UI verification. | implemented |
| 13 | Save modes, recovery, versions | Derivative export, command history, branching, snapshots every 25 revisions, validated document versions, and original preservation exist; incremental/archival/sanitised save-mode coverage is incomplete. | partial |
| 14 | Automated tests for every major tool | 39 tests cover command/session history, scene objects, native text, image/vector reconstruction, page import/geometry, the full supported annotation matrix, threaded comment APIs, AcroForm field/data/flatten flow, secure search redaction, authenticated comparison/overlay rendering, native bookmark and embedded-attachment CRUD/download, live preview, validation, extraction/conversion, security, and export, but not yet every enterprise studio. | missing |
| 15 | Clear unsupported explanations | Capability limitations and classified validation errors exist but coverage is incomplete | partial |
| 16 | Recoverable originals | Source files are immutable and outputs are derivatives | implemented |
| 17 | No primary placeholders | Missing primary tools are mostly not exposed; current PDF Studio still exposes only a small subset | partial |
| 18 | Fully offline after installation | Core local processing and Compose are offline-capable; no offline bundle/SBOM/checksum validation or full offline acceptance run | partial |
| 19 | No silent damage to complex PDFs | Originals are preserved and signature warnings exist; no compatibility corpus or unchanged-page fidelity scoring | unverified |
| 20 | Validate saved output before success | Every editor export is reopened, rendered on changed pages, parsed with strict pypdf, checked for page count/fonts/text/object edits and untouched-page pixel hashes, and stored with a validation report. Form/signature/advanced-colour validation remains incomplete. | partial |

## Architecture and feature domains

| Domain | Status | Missing proof or implementation |
|---|---|---|
| Native document model and scene graph | partial | Stable session IDs, text/image/vector/annotation/field/link objects, resources, boxes, paint order, bookmarks, attachments, OCGs, editability, and source references exist; advanced layer hierarchy and complete operator mapping remain. |
| Editor command system | implemented | Persisted serialized commands, idempotency, optimistic concurrency, undo/redo, branching, recovery snapshots, audit logs, live preview, and versioned validated export are operational. |
| Native text engine | partial | Character mapping, range editing, glyph checks, font policy, baseline/style preservation, and multiple reflow policies exist; paragraph reconstruction, complex shaping, and collision UI remain. |
| Font subsystem | partial | Installed font list, embedded-font glyph checks, explicit preserve/substitute/cancel policy, and Type 3 protection exist; embedding-right enforcement, advanced script shaping, and complete substitution rules remain. |
| Existing image editor | partial | Stable object selection, transform, arbitrary rotation, crop, replace/delete, live preview, undo/redo, and export validation exist; direct content-stream transform and full mask/colour-space corpus remain. |
| Existing vector editor | partial | Stable path objects, safe reconstruction, move/resize/rotate/restyle/delete and protected-object explanations exist; node-level editing, clipping/shading, and overlap isolation remain. |
| Object selection/layers | missing | Handles, marquee/multi-select, z-order, guides, snapping, layers panel |
| Page organiser/content tools | partial | Native cross-PDF insert/replace, reorder, blank insert, delete, rotate, crop, resize/scaling, and all five page boxes exist; visual drag/drop, labels/transitions, advanced layout, and Bates tools remain. |
| Annotation/comments/review | partial | The full supported annotation matrix, file attachments, stable IDs, properties, replies, statuses, filtering/sorting, comments UI, undo/redo, live preview, and export validation exist. Audio is reported unsupported by the local engine; XFDF/FDF import/export and multi-user collaboration remain. |
| OCR Studio | partial | Local OCR adapters exist; region OCR, confidence model/review, searchable-editable reconstruction absent |
| Redaction Studio | partial | True region and selected-page batch search/pattern redaction, PII presets, custom regex, image-pixel removal, hidden-text/JavaScript scrub, optional metadata/comments/attachments/form cleanup, UI, and validation reports exist. OCR-region targeting, repeated-header detection, and hostile alternate-stream verification remain. |
| Sanitisation | partial | Metadata/actions/embedded active content cleanup exists; inspection report and complete removal matrix absent |
| Forms Studio | partial | Ten native field variants, extensive field properties, required/regex validation, safe calculation metadata, tab ordering, JSON/CSV/XFDF data export, bulk import, reset, signature placeholders, and selected/all flattening exist. Automatic detection/alignment/duplication UI, FDF import, barcode support, and richer designer controls remain. |
| Signature/certificate Studio | missing | Certificate storage policy, PKCS#12 signing, trust/timestamp/modification validation absent |
| Comparison | partial | Text-aware word diffs, moved text blocks, font/style changes, page insertion/deletion/movement, image/annotation/form/signature/metadata changes, full visual deltas, authenticated side-by-side and red-overlay rendering, type filters, difference navigation, review marking, and JSON reports exist. Selected-region ignores and persistent/shared review state remain. |
| Conversion/PDF creation | partial | Broad local conversion exists; PDF-to-Office and full creation workspace absent |
| Measurement/technical tools | partial | Native PDF line measurements persist `/Measure` scale/unit dictionaries and render in the editor; interactive calibration presets, area/perimeter tools, snapping, and reports remain. |
| Accessibility/PDF standards | missing | Tagged structure editing, reports, veraPDF/PDF-A workflows, PDF/UA validation absent |
| Security/permissions | partial | AES passwords and app auth exist; PDF permissions, malware scanning, safe-mode policy/report incomplete |
| Attachments/bookmarks/layers/navigation | partial | Native hierarchical bookmark add/update/subtree-delete and embedded attachment add/replace/delete/list/authenticated download are recoverable commands with Studio UI and tests. Link creation exists. Page labels, destinations beyond page jumps, and editable optional-content layers remain. |
| Print production/colour | missing | ICC/output intent/CMYK/overprint/transparency/preflight absent |
| Optimisation | partial | Compression profiles/repair/linearisation exist; space audit and advanced controls absent |
| Batch workflow builder | missing | No persisted workflow/action-run/report system |
| Collaboration/enterprise roles | partial | Users/admin/audit exist; full RBAC, workspaces, locks, review collaboration absent |
| Performance | unverified | No large-document benchmarks, virtualised canvas, tile cache, memory/cancellation corpus |
| WCAG 2.2 AA application | unverified | Responsive semantic UI exists but no automated/manual WCAG evidence |
| Security hardening | partial | Non-root hardened workers exist; network restriction, caps/resource limits, hostile corpus and scanner absent |
| Compatibility/regression corpus | missing | No Office/scanner/CAD/forms/signature/layers corpus or visual regression harness |
| Operational deliverables | partial | Compose, migrations, backup docs/scripts exist; SBOM, licence inventory, upgrade/rollback bundle incomplete |

## Immediate architectural sequence

1. **Completed:** PDF documents, versions, edit sessions, persistent commands, undo/redo, idempotency, snapshots, branching, and audit linkage.
2. **Completed foundation:** session-stable scene graph for text, images, drawings, links, annotations, fields, page boxes, resources, security, bookmarks, attachments, and OCG inspection.
3. **Completed foundation:** Studio command/session authority, object-ID editing, live previews, and validated version export.
4. **In progress:** deepen content-stream-aware text/image/vector mutation and compatibility fidelity beyond safe reconstruction.
5. Add the remaining primary studios and acceptance corpus; only then perform the final requirement-by-requirement completion report.
