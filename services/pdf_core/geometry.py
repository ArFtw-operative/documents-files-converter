"""The single place where PyMuPDF page space is converted to canonical PDF user space (§8.3).

PyMuPDF reports geometry in "MuPDF space" (top-left origin, y down). Analysis and mutation always
run with the page's /Rotate temporarily set to 0 (see ``unrotated``), so MuPDF space is the
unrotated page and ``~page.transformation_matrix`` maps it to PDF user space.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import pymupdf as fitz


@contextmanager
def unrotated(page: fitz.Page) -> Iterator[fitz.Page]:
    rotation = page.rotation
    if rotation:
        page.set_rotation(0)
    try:
        yield page
    finally:
        if rotation:
            page.set_rotation(rotation)


class PageSpace:
    """Converters between MuPDF space of an unrotated page and PDF user space."""

    def __init__(self, page: fitz.Page):
        self.to_pdf = ~page.transformation_matrix
        self.to_mupdf = page.transformation_matrix

    def point(self, x: float, y: float) -> tuple[float, float]:
        p = fitz.Point(x, y) * self.to_pdf
        return (round(p.x, 3), round(p.y, 3))

    def rect(self, r: Sequence[float]) -> list[float]:
        rect = fitz.Rect(r) * self.to_pdf
        rect.normalize()
        return [round(rect.x0, 3), round(rect.y0, 3), round(rect.x1, 3), round(rect.y1, 3)]

    def quad(self, points: Sequence[tuple[float, float]]) -> list[float]:
        out: list[float] = []
        for x, y in points:
            out.extend(self.point(x, y))
        return out

    def pdf_rect_to_mupdf(self, r: Sequence[float]) -> fitz.Rect:
        rect = fitz.Rect(r) * self.to_mupdf
        rect.normalize()
        return rect

    def pdf_point_to_mupdf(self, x: float, y: float) -> fitz.Point:
        return fitz.Point(x, y) * self.to_mupdf


def glyph_quad(origin: tuple[float, float], direction: tuple[float, float], advance: float,
               ascent: float, descent: float) -> list[tuple[float, float]]:
    """Quad of one glyph cell in MuPDF space (y down). ``descent`` is negative."""
    dx, dy = direction
    # Perpendicular "up" vector in y-down space for a left-to-right baseline.
    ux, uy = dy, -dx
    ox, oy = origin
    bottom_start = (ox + ux * descent, oy + uy * descent)
    top_start = (ox + ux * ascent, oy + uy * ascent)
    bottom_end = (bottom_start[0] + dx * advance, bottom_start[1] + dy * advance)
    top_end = (top_start[0] + dx * advance, top_start[1] + dy * advance)
    return [bottom_start, bottom_end, top_end, top_start]


def projection(point: tuple[float, float], origin: tuple[float, float],
               direction: tuple[float, float]) -> float:
    return (point[0] - origin[0]) * direction[0] + (point[1] - origin[1]) * direction[1]


def rotation_degrees_pdf(direction_mupdf: tuple[float, float]) -> float:
    """Counter-clockwise text angle in PDF space for a MuPDF-space writing direction."""
    dx, dy = direction_mupdf
    return round(math.degrees(math.atan2(-dy, dx)), 3) % 360


def union(rects: Sequence[Sequence[float]]) -> list[float]:
    return [min(r[0] for r in rects), min(r[1] for r in rects),
            max(r[2] for r in rects), max(r[3] for r in rects)]


def quad_bbox(quad: Sequence[float]) -> list[float]:
    xs, ys = quad[0::2], quad[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]
