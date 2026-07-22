# PDF Studio acceptance evidence

This record covers the controls exposed by the current PDF Studio interface. It distinguishes tested behavior from future Acrobat-parity work documented in `known-limitations.md`.

## Proven controls and services

| Area | Proven behavior |
|---|---|
| Existing text | A page text block opens with one click in Edit mode. The caret is placed near the click, typing is live in the page, Enter adds a paragraph line, Escape cancels, and Ctrl/Cmd+Enter commits. The editor follows the rendered PDF scale and does not inherit the application's large textarea minimum height. |
| Paragraph save | The API addresses a stable scene object, validates the command before storing it, removes the original text operators, reflows replacement text inside the original region, and leaves searchable PDF text. |
| Font handling | Scene data reports detected family, size, style, color, and available installed families. Subset family names are normalized; reusable embedded fonts are preferred, then a same-family full font, then the explicit substitution policy. Containers install Noto, Liberation, and DejaVu families and populate `/data/fonts`. |
| New text and shapes | Pending objects render as live page overlays while typing or changing style. They can be removed before save and become native PDF operations after save. Rectangle, ellipse, and line previews honor border, fill, width, and opacity. |
| Links | Existing links are selectable overlays. Link create, target/page update, rectangle update, and delete are wired to recoverable commands and covered by unit tests. |
| Pages | Reorder, insert blank, duplicate, delete, rotate, and crop commands are real engine operations and participate in undo/redo. |
| Forms and annotations | Native fields and supported annotation types are created through engine operations, remain interactive unless flattened, and are included in scene data. Form reset restores the PDF default value rather than only changing the browser preview. |
| OCR | The capability response reports languages actually installed in Tesseract, and the UI only offers those languages. OCR work is handled by the PDF worker and reports an explicit failure if the required binary or language is absent. |
| Sessions and recovery | Project operations seed a recreated workspace session, preventing a stale server session from replacing newer saved project history. Access tokens refresh automatically once and the failed request is retried. |
| Export | Export runs in the background, reopens the output, strictly parses it, renders changed pages, and validates operation-specific regional text/object expectations. Later overlapping destructive edits correctly supersede earlier expectations. |

## Verification performed on 19 July 2026

- 45 Python unit, security, engine, and authenticated integration tests passed.
- The Next.js optimized production build compiled successfully and passed TypeScript checking.
- In-browser acceptance confirmed a compact one-click inline editor with a real caret, detected `LiberationSans-Bold`, 20 pt source styling, live text-box typing/removal, and live shape preview/removal.
- A real 31-page export completed at 100%. Strict parsing reported 31 pages, 7 links, an interactive text form field, and searchable `English Translated` title text using `LiberationSans-Bold` at 20 pt. Page 1 was rendered and visually inspected.
- Docker image execution was not performed because Docker is not installed on this development host. Dockerfiles now install the declared OCR language packs and open-source font families; container startup remains an operator acceptance step.

## Acceptance boundary

The application does not claim mathematically perfect OCR, ownership of commercial font files, or complete handling of every possible PDF content stream. Unsupported/protected structures must fail explicitly while the immutable source remains recoverable. See `known-limitations.md` for the remaining certificate-signing, print-production, accessibility, collaboration, complex-shaping, and compatibility-corpus work.
