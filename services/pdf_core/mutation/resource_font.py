"""Reuse a page's existing *non-embedded* font resource for replacement text (architecture §13.2).

Many office PDFs reference standard fonts (Courier New, Arial, Times New Roman…) without embedding
them; every viewer substitutes its own copy. Re-embedding a look-alike would make the edited run
render differently from its neighbours on machines that have the real font. Instead the new text
is written with the *same* font resource, so it is drawn by exactly the same mechanism as the
original. Used only for simple fonts with plain WinAnsi encoding; anything else falls back to the
embedding path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pymupdf as fitz

from ..fonts.resolver import FontResolver, ResolvedFont

_SIMPLE = {"Type1", "TrueType", "MMType1"}


@dataclass
class ResourceFont:
    xref: int
    refname: str
    first_char: int
    widths: list[float] | None  # 1/1000 text-space units, from /Widths
    metrics: ResolvedFont | None  # installed equivalent, used when /Widths is absent

    def encode(self, text: str) -> bytes | None:
        try:
            return text.encode("cp1252")
        except UnicodeEncodeError:
            return None

    def advance(self, code: int, char: str) -> float:
        """Glyph advance in text-space units per 1 pt of font size."""
        if self.widths is not None:
            index = code - self.first_char
            if 0 <= index < len(self.widths) and self.widths[index] > 0:
                return self.widths[index] / 1000
        if self.metrics is not None:
            return self.metrics.font.glyph_advance(ord(char))
        return 0.5

    def width(self, data: bytes, text: str, size: float, tracking: float) -> float:
        total = sum(self.advance(code, char) for code, char in zip(data, text, strict=True)) * size
        return total + tracking * max(0, len(data) - 1)


def _numbers(document: fitz.Document, value: tuple[str, str]) -> list[float] | None:
    kind, raw = value
    if kind == "xref":
        raw = document.xref_object(int(raw.split()[0]))
    elif kind != "array":
        return None
    try:
        return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", raw)]
    except ValueError:
        return None


def find(document: fitz.Document, page: fitz.Page, xref: int | None, style: dict,
         resolver: FontResolver) -> ResourceFont | None:
    if not xref:
        return None
    for fxref, ext, subtype, _basefont, refname, encoding, referencer in page.get_fonts(full=True):
        if fxref == xref:
            break
    else:
        return None
    # Only fonts the page references directly (not via a Form XObject), not embedded, WinAnsi.
    if ext != "n/a" or subtype not in _SIMPLE or referencer != 0 or encoding != "WinAnsiEncoding":
        return None
    if "/Differences" in document.xref_object(xref):
        return None
    first = document.xref_get_key(xref, "FirstChar")
    widths = _numbers(document, document.xref_get_key(xref, "Widths"))
    metrics = resolver.system(style.get("font_family") or "", bool(style.get("bold")), bool(style.get("italic")),
                              bool(style.get("serif")), bool(style.get("mono")))
    return ResourceFont(xref, refname, int(first[1]) if first[0] == "int" else 0, widths, metrics)


def _name(value: str) -> str:
    return "".join(ch if 0x21 <= ord(ch) <= 0x7E and ch not in "()<>[]{}/%#" else f"#{ord(ch):02X}" for ch in value)


def _string(data: bytes) -> str:
    out = []
    for byte in data:
        if byte in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(byte))
        elif 0x20 <= byte < 0x7F:
            out.append(chr(byte))
        else:
            out.append(f"\\{byte:03o}")
    return "".join(out)


def _color(components: list[float]) -> str:
    values = " ".join(f"{max(0.0, min(1.0, v)):.4g}" for v in components)
    fill, stroke = {1: ("g", "G"), 3: ("rg", "RG"), 4: ("k", "K")}.get(len(components), ("g", "G"))
    if len(components) not in (1, 3, 4):
        values = "0"
    return f"{values} {fill} {values} {stroke}"


def write(document: fitz.Document, page: fitz.Page, font: ResourceFont, data: bytes,
          origin_pdf: tuple[float, float], direction_pdf: tuple[float, float], size: float,
          tracking: float, hscale: float, color: list[float], render_mode: int) -> None:
    """Append ``BT … Tj ET`` drawing ``data`` with the existing font resource. PDF user space."""
    cos, sin = direction_pdf
    content = (
        "q BT\n"
        f"/{_name(font.refname)} {size:.4f} Tf\n"
        f"{tracking:.4f} Tc 0 Tw {hscale * 100:.3f} Tz {render_mode} Tr\n"
        f"{_color(color or [0.0])}\n"
        f"{cos:.6f} {sin:.6f} {-sin:.6f} {cos:.6f} {origin_pdf[0]:.4f} {origin_pdf[1]:.4f} Tm\n"
        f"({_string(data)}) Tj\nET Q\n"
    ).encode("latin-1")
    if not page.is_wrapped:
        page.wrap_contents()
    stream = document.get_new_xref()
    document.update_object(stream, "<<>>")
    document.update_stream(stream, content)
    contents = [*page.get_contents(), stream]
    document.xref_set_key(page.xref, "Contents", "[" + " ".join(f"{x} 0 R" for x in contents) + "]")
    _ensure_resource(document, page, font)


def _ensure_resource(document: fitz.Document, page: fitz.Page, font: ResourceFont) -> None:
    """Redaction cleanup can drop a font the page no longer uses; put it back if needed."""
    if any(entry[0] == font.xref and entry[4] == font.refname for entry in page.get_fonts(full=True)):
        return
    kind, value = document.xref_get_key(page.xref, "Resources")
    key = f"Font/{_name(font.refname)}"
    if kind == "xref":
        document.xref_set_key(int(value.split()[0]), key, f"{font.xref} 0 R")
    else:
        document.xref_set_key(page.xref, f"Resources/{key}", f"{font.xref} 0 R")
