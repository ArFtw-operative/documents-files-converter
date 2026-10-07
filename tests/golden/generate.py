"""Deterministic golden PDFs for the document-engine test suite (architecture §70).

Every fixture is generated from open fonts so the suite runs anywhere the API image runs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pymupdf as fitz


def font_file(pattern: str) -> str:
    return subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True,
                          check=True).stdout


def _invoice_page(page: fitz.Page) -> None:
    page.insert_font(fontname="SB", fontfile=font_file("Liberation Sans:bold"))
    page.insert_font(fontname="SR", fontfile=font_file("Liberation Sans"))
    page.insert_text((50, 70), "VISHNU MEDICAL HALL", fontname="SB", fontsize=16, color=(0.1, 0.2, 0.5))
    page.insert_text((50, 92), "12 Market Road, Kochi", fontname="SR", fontsize=9)
    page.insert_text((50, 130), "Invoice No:", fontname="SB", fontsize=10)
    page.insert_text((115, 130), "INV-2026-0042", fontname="SR", fontsize=10)
    page.insert_text((50, 146), "GSTIN:", fontname="SB", fontsize=10)
    page.insert_text((115, 146), "32ABCDE1234F1Z5", fontname="SR", fontsize=10)
    # Line-item table with right-aligned amounts.
    top, row_h = 190, 18
    headers = [("Item", 55), ("Qty", 300), ("Amount", 470)]
    page.draw_rect(fitz.Rect(50, top - 14, 545, top + row_h * 4), color=(0, 0, 0), width=0.6)
    for label, x in headers:
        page.insert_text((x, top), label, fontname="SB", fontsize=10)
    rows = [("Paracetamol 500mg", "2", "120.00"), ("Amoxicillin 250mg", "1", "4553.00"),
            ("Vitamin C", "10", "85.50")]
    for i, (item, qty, amount) in enumerate(rows, start=1):
        y = top + row_h * i
        page.draw_line((50, y - 13), (545, y - 13), color=(0, 0, 0), width=0.4)
        page.insert_text((55, y), item, fontname="SR", fontsize=10)
        page.insert_text((300, y), qty, fontname="SR", fontsize=10)
        width = fitz.get_text_length(amount, fontname="helv", fontsize=10)
        page.insert_text((535 - width, y), amount, fontname="SR", fontsize=10)
    page.insert_text((400, top + row_h * 5 + 6), "Total:", fontname="SB", fontsize=11)
    page.insert_text((480, top + row_h * 5 + 6), "4758.50", fontname="SB", fontsize=11)


def simple_invoice(path: Path) -> Path:
    doc = fitz.open()
    _invoice_page(doc.new_page(width=595, height=842))
    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)
    return path


def rotated_text(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="SR", fontfile=font_file("Liberation Serif"))
    page.insert_text((300, 400), "Rotated label", fontname="SR", fontsize=12, rotate=90)
    page.insert_text((50, 100), "Horizontal neighbour", fontname="SR", fontsize=12)
    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)
    return path


def rotated_page(path: Path) -> Path:
    doc = fitz.open()
    _invoice_page(doc.new_page(width=595, height=842))
    doc[0].set_rotation(90)
    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)
    return path


def cropped_page(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    _invoice_page(page)
    page.set_cropbox(fitz.Rect(30, 40, 565, 700))
    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)
    return path


def base14_text(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), "Plain Helvetica text", fontname="helv", fontsize=12)
    page.insert_text((72, 130), "Times body copy", fontname="tiro", fontsize=12)
    doc.save(path, garbage=3, deflate=True)
    return path


def multipage(path: Path, pages: int = 3) -> Path:
    doc = fitz.open()
    for _ in range(pages):
        _invoice_page(doc.new_page(width=595, height=842))
    doc.subset_fonts()
    doc.save(path, garbage=3, deflate=True)
    return path


ALL = {
    "simple_invoice.pdf": simple_invoice,
    "rotated_text.pdf": rotated_text,
    "rotated_page.pdf": rotated_page,
    "cropped_page.pdf": cropped_page,
    "base14_text.pdf": base14_text,
    "multipage.pdf": multipage,
}


def build_all(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return {name: factory(directory / name) for name, factory in ALL.items()}
