# Supported formats

Runtime `GET /api/v1/capabilities` is authoritative because binary availability varies by image. The standard worker image installs LibreOffice, Pandoc, Tesseract, qpdf, Ghostscript, libheif, and the Python adapters.

- Images: JPEG/JPG, PNG, WebP, GIF, TIFF/TIF, BMP, ICO, HEIC, and HEIF can be read where Pillow/libheif reports support. Outputs are JPEG, PNG, WebP, TIFF, BMP, GIF, and PDF where the source mode is compatible.
- PDF suite: render one or all pages, extract structured/selectable text, OCR scans where OCRmyPDF/Tesseract is installed, extract page ranges and embedded images, rotate, merge, split, compress, remove metadata, encrypt/decrypt with AES-256, add page numbers, flatten forms/annotations, rebuild damaged object structure, and sanitize active content.
- PDF Studio: organize/crop pages; inspect and replace existing text; add text, installed-font content, images, shapes, drawings, links, visual signatures, fields, metadata, watermarks, and headers/footers; annotate; and permanently redact. Exports are new validated PDFs and never overwrite the source.
- Structured extraction: PDF, DOCX, ODT, RTF, TXT, Markdown, HTML, CSV, TSV, XLSX, PPTX, EPUB, JPEG, PNG, WebP, GIF, TIFF, BMP, HEIC, and HEIF to TXT or Markdown. Tables retain tab-separated cells where the source exposes structure.
- Office: LibreOffice advertises conversions for DOC/DOCX/ODT/RTF/TXT/HTML, XLS/XLSX/ODS/CSV, and PPT/PPTX/ODP into formats its installed filters support. The current registry uses a conservative family list; engine failures preserve originals.
- Markup: Pandoc supports Markdown, HTML, text, DOCX, EPUB, ODT, and RTF into its installed writer formats. PDF additionally requires a suitable PDF engine.

Invalid source/target pairs are rejected before worker execution. The capability response includes options, lossless targets, approximation flags, and limitations.
