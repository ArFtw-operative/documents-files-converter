"""Revision validation (architecture §32, §43, §89B.4).

1. Reopen with PyMuPDF and check the page count.
2. qpdf structural check (errors fail; warnings are recorded).
3. Render changed pages before/after and require pixels outside the edited regions to be unchanged.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pymupdf as fitz

from ..geometry import PageSpace, unrotated

RENDER_ZOOM = 1.5
REGION_MARGIN_PT = 2.0
PIXEL_TOLERANCE = 48  # grayscale delta that counts as a changed pixel
MAX_DRIFT_PIXELS = 12


@dataclass
class ValidationReport:
    ok: bool
    page_count: int = 0
    qpdf: str = "skipped"
    qpdf_messages: list[str] = field(default_factory=list)
    visual: dict[int, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "page_count": self.page_count, "qpdf": self.qpdf,
                "qpdf_messages": self.qpdf_messages[:20], "visual": self.visual, "errors": self.errors}


def qpdf_check(path: Path) -> tuple[str, list[str]]:
    binary = shutil.which("qpdf")
    if binary is None:
        return "unavailable", []
    proc = subprocess.run([binary, "--check", str(path)], capture_output=True, text=True, timeout=120,
                          check=False)
    lines = [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
    status = {0: "ok", 3: "warnings"}.get(proc.returncode, "errors")
    return status, lines


def _render(page: fitz.Page) -> tuple[np.ndarray, fitz.Matrix]:
    with unrotated(page):
        matrix = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False, annots=True)
        to_pixels = page.transformation_matrix * matrix
    array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return array, to_pixels


def visual_drift(before: fitz.Page, after: fitz.Page, regions: list[list[float]]) -> dict:
    """Count changed pixels outside the expected edit regions (PDF-space rects)."""
    a, to_pixels = _render(before)
    b, _ = _render(after)
    if a.shape != b.shape:
        return {"drift_pixels": -1, "reason": "page_size_changed"}
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)) > PIXEL_TOLERANCE
    changed_inside = 0
    for region in regions:
        rect = fitz.Rect(region[0] - REGION_MARGIN_PT, region[1] - REGION_MARGIN_PT,
                         region[2] + REGION_MARGIN_PT, region[3] + REGION_MARGIN_PT) * to_pixels
        rect.normalize()
        x0, y0 = max(0, int(rect.x0)), max(0, int(rect.y0))
        x1, y1 = min(diff.shape[1], int(rect.x1) + 1), min(diff.shape[0], int(rect.y1) + 1)
        if x1 > x0 and y1 > y0:
            changed_inside += int(diff[y0:y1, x0:x1].sum())
            diff[y0:y1, x0:x1] = False
    drift = int(diff.sum())
    return {"drift_pixels": drift, "changed_pixels_in_region": changed_inside}


def validate_revision(before_path: Path, after_path: Path, expected_pages: int,
                      changed: dict[int, tuple[int, list[list[float]]]]) -> ValidationReport:
    """``changed`` maps a page index in ``after`` to (page index in ``before``, edit regions)."""
    report = ValidationReport(ok=True)
    try:
        after = fitz.open(after_path)
    except Exception as exc:  # noqa: BLE001
        return ValidationReport(ok=False, errors=[f"reopen_failed: {exc}"])
    with after:
        report.page_count = after.page_count
        if after.page_count != expected_pages:
            report.ok = False
            report.errors.append(f"page_count {after.page_count} != expected {expected_pages}")
        report.qpdf, report.qpdf_messages = qpdf_check(after_path)
        if report.qpdf == "errors":
            report.ok = False
            report.errors.append("qpdf_structural_errors")
        if changed:
            with fitz.open(before_path) as before:
                for after_index, (before_index, regions) in changed.items():
                    try:
                        after[after_index].get_text("text")  # forces content parsing
                        result = visual_drift(before[before_index], after[after_index], regions)
                    except Exception as exc:  # noqa: BLE001
                        report.ok = False
                        report.errors.append(f"render_failed page {after_index}: {exc}")
                        continue
                    report.visual[after_index] = result
                    if result["drift_pixels"] > MAX_DRIFT_PIXELS:
                        report.ok = False
                        report.errors.append(f"unexpected_visual_change page {after_index}")
    return report


def page_space(page: fitz.Page) -> PageSpace:
    with unrotated(page):
        return PageSpace(page)
