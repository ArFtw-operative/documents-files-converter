import zipfile

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

from convertvault.engines.base import ConversionContext
from convertvault.engines.pdf import PdfEngine, TesseractPdfOcrEngine


def make_pdf(path, pages=1, text="ConvertVault"):
    document = fitz.open()
    for number in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"{text} {number + 1}")
    document.set_metadata({"author": "Private author"})
    document.save(path)


def context(source, destination, operation, options=None, additional=None):
    return ConversionContext(source, destination, "pdf", destination.suffix.lstrip("."),
                             {**(options or {}), "_operation": operation}, additional or [])


def test_merge_and_split_are_real_pdf_operations(tmp_path):
    first, second, merged = tmp_path / "first.pdf", tmp_path / "second.pdf", tmp_path / "merged.pdf"
    make_pdf(first, 2); make_pdf(second, 1)
    PdfEngine().convert(context(first, merged, "pdf.merge", additional=[second]))
    assert len(PdfReader(merged).pages) == 3
    archive = tmp_path / "split.zip"
    PdfEngine().convert(context(merged, archive, "pdf.split", {"pages": "every"}))
    with zipfile.ZipFile(archive) as split:
        assert split.namelist() == ["page-0001.pdf", "page-0002.pdf", "page-0003.pdf"]


def test_render_all_and_extract_images_archive_are_valid(tmp_path):
    source, rendered = tmp_path / "input.pdf", tmp_path / "pages.zip"
    make_pdf(source, 2)
    PdfEngine().convert(context(source, rendered, "pdf.render_all", {"format": "png", "dpi": 72}))
    with zipfile.ZipFile(rendered) as archive:
        assert archive.namelist() == ["page-0001.png", "page-0002.png"]
        assert archive.read("page-0001.png").startswith(b"\x89PNG")


def test_compress_metadata_page_numbers_and_password_round_trip(tmp_path):
    source = tmp_path / "source.pdf"; make_pdf(source, 2)
    compressed = tmp_path / "compressed.pdf"
    PdfEngine().convert(context(source, compressed, "pdf.compress", {"remove_metadata": True}))
    assert len(PdfReader(compressed).pages) == 2
    numbered = tmp_path / "numbered.pdf"
    PdfEngine().convert(context(compressed, numbered, "pdf.page_numbers", {"start": 3, "position": "bottom-right"}))
    assert len(PdfReader(numbered).pages) == 2
    encrypted = tmp_path / "encrypted.pdf"
    PdfEngine().convert(context(numbered, encrypted, "pdf.encrypt", {"password": "strong-pass"}))
    assert PdfReader(encrypted).is_encrypted
    decrypted = tmp_path / "decrypted.pdf"
    PdfEngine().convert(context(encrypted, decrypted, "pdf.decrypt", {"password": "strong-pass"}))
    assert not PdfReader(decrypted).is_encrypted and len(PdfReader(decrypted).pages) == 2


def test_flatten_repair_and_sanitize_produce_clean_valid_pdfs(tmp_path):
    source = tmp_path / "interactive.pdf"
    make_pdf(source)
    with fitz.open(source) as original:
        page = original[0]
        widget = fitz.Widget(); widget.field_name = "approval"; widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.rect = fitz.Rect(50, 100, 220, 130); widget.field_value = "Approved"; page.add_widget(widget)
        page.add_text_annot((50, 160), "Review note")
        original.save(tmp_path / "with-fields.pdf")
    source = tmp_path / "with-fields.pdf"

    flattened = tmp_path / "flattened.pdf"
    PdfEngine().convert(context(source, flattened, "pdf.flatten"))
    with fitz.open(flattened) as document:
        assert len(list(document[0].widgets() or [])) == 0
        assert "Approved" in document[0].get_text()

    repaired = tmp_path / "repaired.pdf"
    PdfEngine().convert(context(flattened, repaired, "pdf.repair"))
    assert len(PdfReader(repaired).pages) == 1

    sanitized = tmp_path / "sanitized.pdf"
    PdfEngine().convert(context(source, sanitized, "pdf.sanitize"))
    reader = PdfReader(sanitized)
    assert len(reader.pages) == 1
    assert set((reader.metadata or {}).keys()) <= {"/Producer"}


@pytest.mark.skipif(not TesseractPdfOcrEngine().available(), reason="Tesseract is not installed")
def test_tesseract_fallback_builds_a_searchable_pdf_from_a_real_scan(tmp_path):
    image_path = tmp_path / "scan.png"
    image = Image.new("RGB", (1600, 500), "white")
    draw = ImageDraw.Draw(image)
    font_path = r"C:\Windows\Fonts\arial.ttf"
    font = ImageFont.truetype(font_path, 96) if __import__("pathlib").Path(font_path).is_file() else ImageFont.load_default()
    draw.text((90, 170), "SCAN VERIFY 4827", fill="black", font=font)
    image.save(image_path, dpi=(300, 300))
    source, output = tmp_path / "scan.pdf", tmp_path / "searchable.pdf"
    document = fitz.open(); page = document.new_page(width=600, height=220)
    page.insert_image(page.rect, filename=str(image_path)); document.save(source); document.close()
    TesseractPdfOcrEngine().convert(context(source, output, "pdf.ocr", {"language": "eng", "dpi": 300}))
    with fitz.open(output) as searchable:
        text = searchable[0].get_text("text").upper()
        assert "SCAN VERIFY" in text and "4827" in text
