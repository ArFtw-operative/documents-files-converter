"""Font resolution for text replacement (architecture §13.2, §13.3, §64).

Order of preference for every character of the replacement text:

1. The exact embedded font of the edited run. Subset fonts frequently lack a Unicode cmap, so the
   Unicode → glyph map is rebuilt from the document's own text trace and patched into an in-memory
   copy of the font (it never leaves the document processing context).
2. A Fontconfig match for the same family/weight/slant that covers the character.
3. A Fontconfig generic (sans/serif/mono) that covers it.

Substitutions are reported so the UI can say "Original font does not contain ₹" (§68).
"""

from __future__ import annotations

import io
import logging
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache

import pymupdf as fitz

from .names import family_name, strip_subset

log = logging.getLogger(__name__)

_BASE14 = {
    "helvetica": "helv", "helvetica-bold": "hebo", "helvetica-oblique": "heit",
    "helvetica-boldoblique": "hebi", "times-roman": "tiro", "times-bold": "tibo",
    "times-italic": "tiit", "times-bolditalic": "tibi", "courier": "cour", "courier-bold": "cobo",
    "courier-oblique": "coit", "courier-boldoblique": "cobi", "symbol": "symb",
    "zapfdingbats": "zadb",
}


@dataclass
class ResolvedFont:
    font: fitz.Font
    source: str  # embedded | embedded_patched | base14 | system
    name: str
    file: str | None = None

    def covers(self, char: str) -> bool:
        return char.isspace() or bool(self.font.has_glyph(ord(char)))


@dataclass
class Substitution:
    chars: str
    original_font: str
    used_font: str
    reason: str


@dataclass
class FontPlan:
    """Per-character font assignment for one replacement run."""

    chars: list[tuple[str, ResolvedFont | None]]
    substitutions: list[Substitution] = field(default_factory=list)
    primary: ResolvedFont | None = None


def _same_family(a: str, b: str) -> bool:
    def key(name: str) -> str:
        return "".join(ch for ch in family_name(name).lower() if ch.isalnum())
    return key(a) == key(b)


def _fc_match(pattern: str) -> str | None:
    try:
        result = subprocess.run(["fc-match", "-f", "%{file}", pattern], capture_output=True,
                                text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


@lru_cache(maxsize=256)
def _system_font(path: str) -> fitz.Font:
    return fitz.Font(fontfile=path)


def _pattern(family: str, bold: bool, italic: bool, char: str | None = None) -> str:
    parts = [family.replace(":", " ").replace("-", " ")]
    parts.append("weight=bold" if bold else "weight=regular")
    parts.append("slant=italic" if italic else "slant=roman")
    if char and not char.isspace():
        parts.append(f"charset={ord(char):x}")
    return ":".join(parts)


def _patch_cmap(buffer: bytes, unicode_to_gid: dict[str, int], name: str | None = None) -> bytes | None:
    """Return a copy of an sfnt font with a Unicode cmap built from known glyph usage.

    ``name`` (the original PDF font name) is written into the name table so the re-embedded copy
    keeps the document's font identity and later analysis groups it with untouched runs."""
    try:
        from fontTools.ttLib import TTFont, newTable
        from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    except ImportError:  # pragma: no cover - dependency is pinned
        return None
    try:
        tt = TTFont(io.BytesIO(buffer), lazy=False)
        order = tt.getGlyphOrder()
        mapping = {ord(c): order[gid] for c, gid in unicode_to_gid.items()
                   if 0 < gid < len(order) and len(c) == 1}
        if not mapping:
            return None
        bmp = CmapSubtable.newSubtable(4)
        bmp.platformID, bmp.platEncID, bmp.language = 3, 1, 0
        bmp.cmap = {k: v for k, v in mapping.items() if k <= 0xFFFF}
        tables = [bmp]
        if any(k > 0xFFFF for k in mapping):
            full = CmapSubtable.newSubtable(12)
            full.platformID, full.platEncID, full.language = 3, 10, 0
            full.cmap = dict(mapping)
            tables.append(full)
        cmap = newTable("cmap")
        cmap.tableVersion = 0
        cmap.tables = tables
        tt["cmap"] = cmap
        if name and "name" in tt:
            for name_id in (1, 4, 6):
                tt["name"].setName(name, name_id, 3, 1, 0x409)
                tt["name"].setName(name, name_id, 1, 0, 0)
        out = io.BytesIO()
        tt.save(out)
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - malformed embedded fonts are common
        log.info("cmap patch failed: %s", exc)
        return None


class FontResolver:
    """Resolves fonts for one open document. Not shared between documents (§64)."""

    def __init__(self, document: fitz.Document, max_trace_pages: int = 50):
        self.document = document
        self.max_trace_pages = max_trace_pages
        self._usage: dict[str, dict[str, int]] | None = None
        self._embedded: dict[int, ResolvedFont | None] = {}
        self._not_embedded: set[int] = set()  # fonts the PDF only references by name

    # Unicode → glyph id for every font name, learned from the document's text trace.
    def usage(self, font_name: str) -> dict[str, int]:
        if self._usage is None:
            usage: dict[str, dict[str, int]] = {}
            for page in self.document.pages(0, min(self.document.page_count, self.max_trace_pages)):
                for span in page.get_texttrace():
                    table = usage.setdefault(span.get("font") or "", {})
                    for code, gid, *_ in span.get("chars", ()):
                        if code > 0 and gid > 0:
                            table.setdefault(chr(code), int(gid))
            self._usage = usage
        return self._usage.get(font_name, {})

    def embedded(self, xref: int | None, font_name: str) -> ResolvedFont | None:
        if not xref:
            return self._base14(font_name)
        if xref in self._embedded:
            return self._embedded[xref]
        resolved: ResolvedFont | None = None
        try:
            basename, ext, _subtype, buffer = self.document.extract_font(xref)
        except Exception:  # noqa: BLE001
            basename, ext, buffer = font_name, "n/a", b""
        name, _ = strip_subset(basename or font_name)
        if buffer and ext in ("ttf", "otf", "cff"):
            known = self.usage(font_name)
            try:
                font = fitz.Font(fontbuffer=buffer)
                if known and all(font.has_glyph(ord(c)) for c in list(known)[:20]):
                    resolved = ResolvedFont(font, "embedded", name)
            except Exception:  # noqa: BLE001
                font = None
            if resolved is None and ext in ("ttf", "otf") and known:
                patched = _patch_cmap(buffer, known, name)
                if patched:
                    try:
                        resolved = ResolvedFont(fitz.Font(fontbuffer=patched), "embedded_patched", name)
                    except Exception:  # noqa: BLE001
                        resolved = None
        elif not buffer:
            resolved = self._base14(name)
            if resolved is None:
                self._not_embedded.add(xref)
        self._embedded[xref] = resolved
        return resolved

    @staticmethod
    def _base14(font_name: str) -> ResolvedFont | None:
        key = strip_subset(font_name)[0].lower().replace(" ", "")
        code = _BASE14.get(key)
        if code is None:
            return None
        return ResolvedFont(fitz.Font(code), "base14", font_name)

    def system(self, family: str, bold: bool, italic: bool, serif: bool, mono: bool,
               char: str | None = None) -> ResolvedFont | None:
        generic = "monospace" if mono else "serif" if serif else "sans-serif"
        for fam in (family, generic):
            path = _fc_match(_pattern(fam, bold, italic, char))
            if not path:
                continue
            try:
                font = _system_font(path)
            except Exception:  # noqa: BLE001
                continue
            resolved = ResolvedFont(font, "system", font.name, path)
            if char is None or resolved.covers(char):
                return resolved
        return None

    def plan(self, text: str, style: dict, font_xref: int | None) -> FontPlan:
        font_name = style.get("font_name", "")
        family = style.get("font_family") or family_name(font_name)
        bold, italic = bool(style.get("bold")), bool(style.get("italic"))
        serif, mono = bool(style.get("serif")), bool(style.get("mono"))
        primary = self.embedded(font_xref, font_name)
        substitute_for_run: ResolvedFont | None = None
        if primary is None:
            # Original font cannot be reused at all (Type3, bare CFF without names, damaged):
            # use one visually matched family for the whole run rather than mixing.
            substitute_for_run = self.system(family, bold, italic, serif, mono)
        if primary is not None and any(not primary.covers(c) for c in text):
            # Subsets often lack glyphs the edit needs. When the installed copy of the *same family*
            # covers the whole run, use it for every character: identical appearance, one clean
            # span, and no visible substitution warning.
            installed = self.system(family, bold, italic, serif, mono)
            if (installed is not None and _same_family(installed.name, font_name)
                    and all(installed.covers(c) for c in text)):
                return FontPlan([(c, installed) for c in text],
                                [Substitution(text, font_name, installed.name, "same_family_installed")],
                                installed)
        chars: list[tuple[str, ResolvedFont | None]] = []
        substitutions: dict[str, Substitution] = {}
        for char in text:
            chosen = primary if primary and primary.covers(char) else None
            if chosen is None and substitute_for_run and substitute_for_run.covers(char):
                chosen = substitute_for_run
            if chosen is None:
                chosen = self.system(family, bold, italic, serif, mono, char)
            if chosen is not primary and not char.isspace():
                used = chosen.name if chosen else "none"
                if primary:
                    reason = "glyph_missing"
                elif font_xref in self._not_embedded:
                    reason = "not_embedded"  # viewers substitute this font anyway; not a visible change
                else:
                    reason = "font_not_reusable"
                key = f"{used}:{reason}"
                entry = substitutions.setdefault(key, Substitution("", font_name, used, reason))
                if char not in entry.chars:
                    entry.chars += char
            chars.append((char, chosen))
        return FontPlan(chars, list(substitutions.values()), primary or substitute_for_run)
