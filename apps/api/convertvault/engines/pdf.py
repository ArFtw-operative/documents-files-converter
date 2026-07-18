import shutil
import subprocess
import tempfile
import zipfile
import os
from pathlib import Path

import fitz
from pypdf import PdfReader, PdfWriter

from .base import Capability, ConversionContext


class PdfEngine:
    engine_id = "pypdf-fitz"
    display_name = "PDF toolkit"

    def available(self) -> bool:
        return True

    def version(self) -> str:
        import pypdf
        return pypdf.__version__

    def capabilities(self) -> list[Capability]:
        return [
            Capability("pdf.render", ["pdf"], ["png", "jpg", "jpeg", "webp"], self.engine_id,
                       options={"dpi": {"type": "integer", "minimum": 72, "maximum": 600, "default": 144}}),
            Capability("pdf.extract_text", ["pdf"], ["txt"], self.engine_id,
                       limitations=["Scanned pages require the optional OCR engine."]),
            Capability("pdf.extract_pages", ["pdf"], ["pdf"], self.engine_id,
                       options={"pages": {"type": "string", "default": "1"}}),
            Capability("pdf.rotate", ["pdf"], ["pdf"], self.engine_id,
                       options={"rotate": {"type": "integer", "enum": [90, 180, 270]}}),
            Capability("pdf.merge", ["pdf"], ["pdf"], self.engine_id,
                       options={"input_file_ids": {"type": "array", "minimum_items": 2}}),
            Capability("pdf.split", ["pdf"], ["zip"], self.engine_id,
                       options={"pages": {"type": "string", "default": "every"}}),
            Capability("pdf.render_all", ["pdf"], ["zip"], self.engine_id,
                       options={"format": {"type": "string", "enum": ["png", "jpg"], "default": "png"},
                                "dpi": {"type": "integer", "minimum": 72, "maximum": 300, "default": 144}}),
            Capability("pdf.compress", ["pdf"], ["pdf"], self.engine_id,
                       options={"preset": {"type": "string", "enum": ["archival", "print", "balanced", "screen", "maximum"], "default": "balanced"},
                                "remove_metadata": {"type": "boolean", "default": True}}),
            Capability("pdf.remove_metadata", ["pdf"], ["pdf"], self.engine_id),
            Capability("pdf.encrypt", ["pdf"], ["pdf"], self.engine_id,
                       options={"password": {"type": "password", "minimum_length": 8}}),
            Capability("pdf.decrypt", ["pdf"], ["pdf"], self.engine_id,
                       options={"password": {"type": "password"}}),
            Capability("pdf.page_numbers", ["pdf"], ["pdf"], self.engine_id,
                       options={"start": {"type": "integer", "default": 1}, "position": {"type": "string", "enum": ["bottom-center", "bottom-right", "top-right"], "default": "bottom-center"}}),
            Capability("pdf.extract_images", ["pdf"], ["zip"], self.engine_id),
            Capability("pdf.flatten", ["pdf"], ["pdf"], self.engine_id,
                       limitations=["Form fields and annotations become fixed page content and can no longer be edited."]),
            Capability("pdf.repair", ["pdf"], ["pdf"], self.engine_id,
                       limitations=["Rebuilds and cleans the PDF object structure; it cannot recover source data that is already missing."]),
            Capability("pdf.sanitize", ["pdf"], ["pdf"], self.engine_id,
                       limitations=["Removes document metadata, embedded files, document scripts, and interactive actions while retaining page content."]),
        ]

    def convert(self, context: ConversionContext) -> list[Path]:
        operation = context.options.pop("_operation", "pdf.render")
        if operation == "pdf.render":
            document = fitz.open(context.source)
            page = document.load_page(int(context.options.get("page", 1)) - 1)
            dpi = max(72, min(600, int(context.options.get("dpi", 144))))
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            pix.save(context.destination)
        elif operation == "pdf.extract_text":
            document = fitz.open(context.source)
            context.destination.write_text("\n\n".join(page.get_text() for page in document), encoding="utf-8")
        elif operation == "pdf.merge":
            writer = PdfWriter()
            for source in [context.source, *context.additional_sources]:
                reader = PdfReader(str(source))
                if reader.is_encrypted:
                    raise ValueError(f"{source.name} is password-protected")
                for page in reader.pages:
                    writer.add_page(page)
            with context.destination.open("wb") as output:
                writer.write(output)
        elif operation == "pdf.split":
            reader = PdfReader(str(context.source))
            selection = context.options.get("pages", "every")
            groups = [[index] for index in range(len(reader.pages))] if selection == "every" else [[page] for page in parse_pages(selection, len(reader.pages))]
            with zipfile.ZipFile(context.destination, "w", zipfile.ZIP_DEFLATED) as archive:
                for sequence, indexes in enumerate(groups, 1):
                    writer = PdfWriter()
                    for index in indexes: writer.add_page(reader.pages[index])
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temporary:
                        temporary_path = Path(temporary.name)
                    try:
                        with temporary_path.open("wb") as output: writer.write(output)
                        archive.write(temporary_path, f"page-{indexes[0] + 1:04d}.pdf")
                    finally: temporary_path.unlink(missing_ok=True)
        elif operation == "pdf.render_all":
            document = fitz.open(context.source)
            image_format = context.options.get("format", "png").lower()
            dpi = max(72, min(300, int(context.options.get("dpi", 144))))
            with zipfile.ZipFile(context.destination, "w", zipfile.ZIP_DEFLATED) as archive:
                for index, page in enumerate(document):
                    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                    data = pix.tobytes("jpeg" if image_format in {"jpg", "jpeg"} else "png")
                    archive.writestr(f"page-{index + 1:04d}.{image_format}", data)
        elif operation == "pdf.compress":
            document = fitz.open(context.source)
            if document.needs_pass: raise ValueError("The PDF is password-protected")
            if context.options.get("remove_metadata", True): document.set_metadata({})
            document.save(context.destination, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                          clean=True, linear=True)
        elif operation in {"pdf.remove_metadata", "pdf.encrypt", "pdf.decrypt"}:
            reader, writer = PdfReader(str(context.source)), PdfWriter()
            password = str(context.options.get("password", ""))
            if reader.is_encrypted:
                if not password or reader.decrypt(password) == 0: raise ValueError("The supplied PDF password is incorrect")
            for page in reader.pages: writer.add_page(page)
            if operation == "pdf.remove_metadata": writer.add_metadata({})
            elif operation == "pdf.encrypt":
                if len(password) < 8: raise ValueError("Use a PDF password containing at least 8 characters")
                writer.encrypt(password, algorithm="AES-256")
            with context.destination.open("wb") as output: writer.write(output)
        elif operation == "pdf.page_numbers":
            document = fitz.open(context.source); start = int(context.options.get("start", 1)); position = context.options.get("position", "bottom-center")
            for index, page in enumerate(document):
                label = str(start + index); rect = page.rect
                point = {"bottom-center": fitz.Point(rect.width / 2 - len(label) * 3, rect.height - 18),
                         "bottom-right": fitz.Point(rect.width - 40, rect.height - 18),
                         "top-right": fitz.Point(rect.width - 40, 24)}[position]
                page.insert_text(point, label, fontsize=10, color=(0.2, 0.2, 0.2))
            document.save(context.destination, garbage=3, deflate=True)
        elif operation == "pdf.extract_images":
            document = fitz.open(context.source); seen: set[int] = set()
            with zipfile.ZipFile(context.destination, "w", zipfile.ZIP_DEFLATED) as archive:
                for page_index, page in enumerate(document):
                    for image_index, image in enumerate(page.get_images(full=True), 1):
                        xref = image[0]
                        if xref in seen: continue
                        seen.add(xref); extracted = document.extract_image(xref)
                        archive.writestr(f"page-{page_index + 1:04d}-image-{image_index:03d}.{extracted['ext']}", extracted["image"])
            document.close()
        elif operation in {"pdf.flatten", "pdf.repair"}:
            with fitz.open(context.source) as document:
                if document.needs_pass: raise ValueError("The PDF is password-protected")
                if operation == "pdf.flatten":
                    if not hasattr(document, "bake"): raise RuntimeError("This PDF engine does not support flattening")
                    document.bake(annots=True, widgets=True)
                document.save(context.destination, garbage=4, clean=True, deflate=True,
                              deflate_images=True, deflate_fonts=True, linear=True)
        elif operation == "pdf.sanitize":
            reader, writer = PdfReader(str(context.source)), PdfWriter()
            if reader.is_encrypted: raise ValueError("Unlock this PDF before sanitizing it")
            for source_page in reader.pages:
                source_page.pop("/AA", None)
                for reference in source_page.get("/Annots", []):
                    annotation = reference.get_object()
                    annotation.pop("/AA", None); annotation.pop("/A", None)
                    annotation.pop("/JS", None); annotation.pop("/RichMediaContent", None)
                writer.add_page(source_page)
            writer.add_metadata({})
            with context.destination.open("wb") as output: writer.write(output)
        else:
            reader, writer = PdfReader(str(context.source)), PdfWriter()
            pages = parse_pages(context.options.get("pages", ""), len(reader.pages))
            if not pages:
                pages = list(range(len(reader.pages)))
            for index in pages:
                page = reader.pages[index]
                if operation == "pdf.rotate":
                    page.rotate(int(context.options.get("rotate", 90)))
                writer.add_page(page)
            with context.destination.open("wb") as output:
                writer.write(output)
        return [context.destination]


class OcrEngine:
    engine_id = "ocrmypdf"
    display_name = "OCRmyPDF"

    def available(self) -> bool: return shutil.which("ocrmypdf") is not None
    def version(self) -> str:
        if not self.available(): return "unavailable"
        return subprocess.run(["ocrmypdf", "--version"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    def capabilities(self) -> list[Capability]:
        languages = tesseract_languages()
        return [Capability("pdf.ocr", ["pdf"], ["pdf"], self.engine_id, approximate=True,
            options={"language": {"type": "string", "enum": languages, "default": "eng" if "eng" in languages else languages[0]}, "deskew": {"type": "boolean", "default": True}, "rotate_pages": {"type": "boolean", "default": True}},
            limitations=["OCR accuracy depends on scan quality, orientation, typography, and installed language packs."])] if self.available() else []
    def convert(self, context: ConversionContext) -> list[Path]:
        command = ["ocrmypdf", "--skip-text", "--optimize", "1", "--language", str(context.options.get("language", "eng"))]
        if context.options.get("deskew", True): command.append("--deskew")
        if context.options.get("rotate_pages", True): command.append("--rotate-pages")
        command.extend([str(context.source), str(context.destination)])
        subprocess.run(command, capture_output=True, text=True, timeout=1800, check=True)
        return [context.destination]


def tesseract_binary() -> str | None:
    configured = os.environ.get("TESSERACT_CMD")
    candidates = [
        configured,
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe"),
    ]
    return next((str(candidate) for candidate in candidates
                 if candidate and Path(candidate).is_file()), None)


def tesseract_languages() -> list[str]:
    binary = tesseract_binary()
    if not binary:
        return ["eng"]
    try:
        result = subprocess.run([binary, "--list-langs"], capture_output=True, text=True,
                                timeout=10, check=True)
        languages = sorted({line.strip() for line in result.stdout.splitlines()[1:] if line.strip()})
        return languages or ["eng"]
    except (OSError, subprocess.SubprocessError):
        return ["eng"]


class TesseractPdfOcrEngine:
    """Portable scanned-PDF OCR fallback when OCRmyPDF is unavailable."""

    engine_id = "tesseract-pdf"
    display_name = "Tesseract searchable PDF"

    def available(self) -> bool:
        return tesseract_binary() is not None

    def version(self) -> str:
        binary = tesseract_binary()
        if not binary:
            return "unavailable"
        result = subprocess.run([binary, "--version"], capture_output=True, text=True,
                                timeout=10, check=True)
        return (result.stdout or result.stderr).splitlines()[0].strip()

    def capabilities(self) -> list[Capability]:
        if not self.available() or shutil.which("ocrmypdf"):
            return []
        languages = tesseract_languages()
        return [Capability(
            "pdf.ocr", ["pdf"], ["pdf"], self.engine_id, approximate=True,
            options={"language": {"type": "string", "enum": languages,
                                  "default": "eng" if "eng" in languages else languages[0]},
                     "dpi": {"type": "integer", "minimum": 150, "maximum": 600, "default": 300}},
            limitations=[
                "Pages that already contain selectable text are preserved unchanged.",
                "Scanned pages are rebuilt with their image plus a searchable Tesseract text layer.",
                "OCR accuracy depends on scan quality, orientation, typography, and installed language packs.",
            ],
        )]

    def convert(self, context: ConversionContext) -> list[Path]:
        binary = tesseract_binary()
        if not binary:
            raise RuntimeError("Tesseract OCR is not installed")
        language = str(context.options.get("language", "eng"))
        dpi = max(150, min(600, int(context.options.get("dpi", 300))))
        with fitz.open(context.source) as source, fitz.open() as output:
            if source.needs_pass:
                raise ValueError("Unlock this PDF before applying OCR")
            for index, page in enumerate(source):
                if page.get_text("text").strip():
                    output.insert_pdf(source, from_page=index, to_page=index)
                    continue
                pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
                pixmap.set_dpi(dpi, dpi)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temporary:
                    image_path = Path(temporary.name)
                try:
                    pixmap.save(image_path)
                    result = subprocess.run(
                        [binary, str(image_path), "stdout", "-l", language, "pdf"],
                        capture_output=True, timeout=600, check=True,
                    )
                    if not result.stdout.startswith(b"%PDF"):
                        message = result.stderr.decode("utf-8", errors="replace")[:300]
                        raise RuntimeError(f"Tesseract did not produce a searchable PDF page: {message}")
                    with fitz.open(stream=result.stdout, filetype="pdf") as ocr_page:
                        output.insert_pdf(ocr_page)
                finally:
                    image_path.unlink(missing_ok=True)
            if output.page_count != source.page_count:
                raise RuntimeError("OCR output page count does not match the source PDF")
            output.save(context.destination, garbage=4, deflate=True, use_objstms=1)
        with fitz.open(context.destination) as check:
            if check.page_count < 1 or not any(page.get_text("text").strip() for page in check):
                raise RuntimeError("OCR completed but no searchable text layer was produced")
        return [context.destination]


def parse_pages(value: str, count: int) -> list[int]:
    result: set[int] = set()
    for part in value.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start, end = (int(item) for item in part.split("-", 1))
            result.update(range(start - 1, end))
        else:
            result.add(int(part) - 1)
    if any(page < 0 or page >= count for page in result):
        raise ValueError("Selected page is outside this document")
    return sorted(result)
