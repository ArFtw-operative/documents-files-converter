"""Native PDF analysis → Document Scene Graph (architecture §9, §10, §15.1)."""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass, field

import pymupdf as fitz

from ..fonts.names import family_name, is_bold_name, is_italic_name, strip_subset
from ..geometry import PageSpace, glyph_quad, projection, quad_bbox, rotation_degrees_pdf, unrotated
from ..scene import (
    ObjectSource,
    ObjectType,
    PageScene,
    PageType,
    SceneObject,
    TextStyle,
)

# texttrace "type" values
_FILL, _STROKE, _INVISIBLE = 0, 1, 3
_RENDER = {0: "fill", 1: "stroke", 3: "invisible"}

# PyMuPDF font flags (texttrace span "flags")
_F_ITALIC, _F_SERIF, _F_MONO, _F_BOLD = 2, 4, 8, 16


@dataclass
class _Char:
    c: str
    gid: int
    origin: tuple[float, float]
    advance: float
    seqno: int
    index: int  # index inside its texttrace span


@dataclass
class _Span:
    seqno: int
    font: str
    size: float
    color: tuple[float, ...]
    colorspace: int
    opacity: float
    kind: int
    flags: int
    direction: tuple[float, float]
    ascender: float
    descender: float
    space_width: float
    bidi_rtl: bool
    chars: list[_Char] = field(default_factory=list)

    @property
    def style_key(self) -> tuple:
        return (self.font, round(self.size, 1), tuple(round(v, 3) for v in self.color),
                self.kind, round(self.opacity, 2))

    @property
    def baseline(self) -> float:
        """Offset of the baseline along the normal of the writing direction."""
        ox, oy = self.chars[0].origin
        dx, dy = self.direction
        return ox * -dy + oy * dx


@dataclass
class _Run:
    spans: list[_Span]
    chars: list[_Char]
    line_key: int = 0

    @property
    def lead(self) -> _Span:
        """The span contributing most characters defines the run's style."""
        counts: dict[int, int] = {}
        for char in self.chars:
            counts[char.seqno] = counts.get(char.seqno, 0) + 1
        return max(self.spans, key=lambda span: counts.get(span.seqno, 0))


def _hex(components: tuple[float, ...], colorspace: int) -> str:
    if colorspace == 1 or len(components) == 1:
        r = g = b = components[0] if components else 0.0
    elif colorspace == 4 or len(components) == 4:
        c, m, y, k = components
        r, g, b = (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
    else:
        r, g, b = (components + (0.0, 0.0, 0.0))[:3]
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in (r, g, b))


def _stable_id(page_uuid: str, *parts: object) -> str:
    try:
        namespace = uuid.UUID(page_uuid)
    except ValueError:
        namespace = uuid.NAMESPACE_URL
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8", "replace")).hexdigest()[:32]
    return str(uuid.uuid5(namespace, digest))


def _spans(page: fitz.Page) -> list[_Span]:
    spans: list[_Span] = []
    for raw in page.get_texttrace():
        if raw.get("type") not in (_FILL, _STROKE, _INVISIBLE) or not raw.get("chars"):
            continue
        direction = tuple(raw.get("dir") or (1.0, 0.0))
        norm = math.hypot(*direction) or 1.0
        direction = (direction[0] / norm, direction[1] / norm)
        span = _Span(
            seqno=int(raw["seqno"]), font=raw.get("font") or "", size=float(raw.get("size") or 0),
            color=tuple(raw.get("color") or (0.0,)), colorspace=int(raw.get("colorspace") or 1),
            opacity=float(raw.get("opacity") if raw.get("opacity") is not None else 1.0),
            kind=int(raw["type"]), flags=int(raw.get("flags") or 0), direction=direction,
            ascender=float(raw.get("ascender") or 0.9), descender=float(raw.get("descender") or -0.2),
            space_width=float(raw.get("spacewidth") or (raw.get("size") or 10) * 0.25),
            bidi_rtl=bool((raw.get("bidi_lvl") or 0) % 2),
        )
        if span.size <= 0:
            continue
        for index, (code, gid, origin, bbox) in enumerate(raw["chars"]):
            corners = [(bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[2], bbox[3]), (bbox[0], bbox[3])]
            advance = max(projection(p, origin, direction) for p in corners)
            span.chars.append(_Char(chr(code) if code > 0 else "�", int(gid), tuple(origin),
                                    max(0.0, advance), span.seqno, index))
        spans.append(span)
    return spans


def _drop_fake_bold(spans: list[_Span]) -> tuple[list[_Span], dict[int, list[int]]]:
    """Text drawn twice with a tiny offset ("fake bold") becomes one run; duplicates are kept as
    native references so an edit removes both copies."""
    kept: list[_Span] = []
    duplicates: dict[int, list[int]] = {}
    for span in spans:
        text = "".join(c.c for c in span.chars)
        twin = None
        for other in kept[-6:]:
            if other.style_key[:2] != span.style_key[:2] or "".join(c.c for c in other.chars) != text:
                continue
            dx = span.chars[0].origin[0] - other.chars[0].origin[0]
            dy = span.chars[0].origin[1] - other.chars[0].origin[1]
            if math.hypot(dx, dy) < max(0.6, span.size * 0.06):
                twin = other
                break
        if twin is None:
            kept.append(span)
        else:
            duplicates.setdefault(twin.seqno, []).append(span.seqno)
    return kept, duplicates


def _runs(spans: list[_Span]) -> list[_Run]:
    """Cluster spans by direction + baseline, split by style and by column-sized gaps."""
    lines: list[list[_Span]] = []
    for span in sorted(spans, key=lambda s: (round(s.direction[0], 2), round(s.direction[1], 2),
                                            round(s.baseline, 1))):
        for line in lines:
            ref = line[0]
            if (abs(ref.direction[0] - span.direction[0]) < 0.01
                    and abs(ref.direction[1] - span.direction[1]) < 0.01
                    and abs(ref.baseline - span.baseline) <= 0.18 * max(ref.size, span.size)):
                line.append(span)
                break
        else:
            lines.append([span])

    runs: list[_Run] = []
    for line_key, line in enumerate(lines):
        direction = line[0].direction
        anchor = line[0].chars[0].origin
        if any(s.bidi_rtl for s in line):
            # Complex bidi lines keep content order and are not merged (§65 handled later).
            for span in sorted(line, key=lambda s: s.seqno):
                runs.append(_Run([span], list(span.chars), line_key))
            continue

        def at(char: _Char) -> float:
            return projection(char.origin, anchor, direction)

        # 1. Segments: contiguous pieces of one span, split where the span itself jumps by a
        #    column-sized gap (TJ arrays often hold a whole table row).
        segments: list[tuple[_Span, list[_Char]]] = []
        for span in line:
            split_gap = max(0.9 * span.size, 3.0 * span.space_width)
            piece: list[_Char] = []
            for char in span.chars:
                if piece and at(char) - (at(piece[-1]) + piece[-1].advance) > split_gap:
                    segments.append((span, piece))
                    piece = []
                piece.append(char)
            if piece:
                segments.append((span, piece))
        segments.sort(key=lambda seg: at(seg[1][0]))

        # 2. Greedily attach each segment to an open run of the same style that ends just before
        #    it. Overlapping text of another style (e.g. overflowed edits) never interleaves.
        open_runs: list[tuple[_Run, float]] = []
        for span, chars in segments:
            start = at(chars[0])
            split_gap = max(0.9 * span.size, 3.0 * span.space_width)
            best, best_gap = None, None
            for index, (run, end) in enumerate(open_runs):
                gap = start - end
                lead = run.spans[0]
                if lead.style_key == span.style_key:
                    joins = -0.3 * span.size <= gap <= split_gap
                else:
                    # Font fallback inside a word: same size/colour/render mode, glyphs abutting.
                    joins = (lead.style_key[1:] == span.style_key[1:]
                             and -0.05 * span.size <= gap <= 0.15 * span.size)
                if joins and (best_gap is None or abs(gap) < abs(best_gap)):
                    best, best_gap = index, gap
            end = at(chars[-1]) + chars[-1].advance
            if best is None:
                run = _Run([span], list(chars), line_key)
                runs.append(run)
                open_runs.append((run, end))
            else:
                run, _ = open_runs[best]
                if span not in run.spans:
                    run.spans.append(span)
                run.chars.extend(chars)
                open_runs[best] = (run, end)
    return runs


def _trim(chars: list[_Char]) -> list[_Char]:
    start, end = 0, len(chars)
    while start < end and chars[start].c.isspace():
        start += 1
    while end > start and chars[end - 1].c.isspace():
        end -= 1
    return chars[start:end]


def _alignment(objects: list[SceneObject]) -> None:
    """Infer left/right/center alignment from vertically neighbouring runs (§17.3)."""
    horizontal = [o for o in objects if o.type == ObjectType.TEXT_NATIVE
                  and abs(o.style.get("rotation_deg", 0)) < 0.5]
    for obj in horizontal:
        x0, y0, x1, y1 = obj.bbox
        size = obj.style.get("size_pt", 10)
        votes = {"left": 0, "right": 0, "center": 0}
        for other in horizontal:
            if other is obj:
                continue
            ox0, oy0, ox1, oy1 = other.bbox
            if abs(oy0 - y0) > size * 25 or abs(oy0 - y0) < size * 0.5:
                continue
            left, right = abs(ox0 - x0) < 0.75, abs(ox1 - x1) < 0.75
            center = abs((ox0 + ox1) / 2 - (x0 + x1) / 2) < 0.75
            if right and not left:
                votes["right"] += 1
            elif left and not right:
                votes["left"] += 1
            elif center and not left and not right:
                votes["center"] += 1
        best = max(votes, key=lambda key: (votes[key], key == "left"))
        obj.style["text_align"] = best if votes[best] > 0 else "left"


def _font_catalog(page: fitz.Page) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for xref, ext, subtype, basefont, refname, encoding, *_ in page.get_fonts(full=True):
        name, subset = strip_subset(basefont)
        catalog.setdefault(name, {
            "xref": xref, "ext": ext, "subtype": subtype, "basefont": basefont,
            "refname": refname, "encoding": encoding, "subset": subset,
            "embedded": bool(xref) and ext not in ("n/a", ""),
        })
    return catalog


def _text_objects(page: fitz.Page, space: PageSpace, page_uuid: str) -> list[SceneObject]:
    spans, duplicates = _drop_fake_bold(_spans(page))
    fonts = _font_catalog(page)
    objects: list[SceneObject] = []
    for run in _runs(spans):
        chars = _trim(run.chars)
        if not chars:
            continue
        lead = run.lead
        direction = lead.direction
        size = lead.size
        ascent, descent = lead.ascender * size, lead.descender * size
        glyphs: list[dict] = []
        previous_end = None
        for char in chars:
            start = projection(char.origin, chars[0].origin, direction)
            if previous_end is not None and not char.c.isspace() and glyphs and not glyphs[-1]["c"].isspace():
                gap = start - previous_end
                if gap > max(0.18 * size, 0.6 * lead.space_width):
                    gap_origin = (chars[0].origin[0] + direction[0] * previous_end,
                                  chars[0].origin[1] + direction[1] * previous_end)
                    quad = glyph_quad(gap_origin, direction, gap, ascent, descent)
                    glyphs.append({"c": " ", "quad": space.quad(quad), "synthetic": True})
            quad = glyph_quad(char.origin, direction, char.advance, ascent, descent)
            glyphs.append({"c": char.c, "quad": space.quad(quad), "synthetic": False})
            previous_end = start + char.advance
        text = "".join(g["c"] for g in glyphs)
        first, last = chars[0], chars[-1]
        width = projection(last.origin, first.origin, direction) + last.advance
        run_quad = space.quad(glyph_quad(first.origin, direction, width, ascent, descent))
        font_name, subset = strip_subset(lead.font)
        font = fonts.get(font_name, {})
        bold = bool(lead.flags & _F_BOLD) or is_bold_name(font_name)
        italic = bool(lead.flags & _F_ITALIC) or is_italic_name(font_name)
        origin_pdf = space.point(*first.origin)
        pdf_dir = (direction[0], -direction[1])
        rotation = rotation_degrees_pdf(direction)
        span_refs: dict[int, list[int]] = {}
        for char in chars:
            span_refs.setdefault(char.seqno, []).append(char.index)
        native_spans = [{"seqno": seqno, "chars": [min(idx), max(idx) + 1]} for seqno, idx in span_refs.items()]
        for seqno in list(span_refs):
            for twin in duplicates.get(seqno, []):
                native_spans.append({"seqno": twin, "chars": None, "duplicate_of": seqno})
        glyph_count = sum(1 for g in glyphs if not g["synthetic"])
        natural = sum(c.advance for c in chars)
        letter_spacing = 0.0
        if glyph_count > 1:
            letter_spacing = round((width - natural) / (glyph_count - 1), 3)
            # Large positive gaps come from word spacing, not tracking.
            if abs(letter_spacing) > 0.2 * size:
                letter_spacing = 0.0
        style = TextStyle(
            font_name=font_name, font_family=family_name(font_name),
            font_key=f"xref:{font['xref']}" if font.get("xref") else None,
            embedded=bool(font.get("embedded")), subset=subset or bool(font.get("subset")),
            bold=bold, italic=italic, serif=bool(lead.flags & _F_SERIF), mono=bool(lead.flags & _F_MONO),
            size_pt=round(size, 3), fill=_hex(lead.color, lead.colorspace) if lead.kind != _STROKE else None,
            fill_components=[round(v, 5) for v in lead.color], stroke=_hex(lead.color, lead.colorspace) if lead.kind == _STROKE else None,
            render_mode=_RENDER.get(lead.kind, "fill"), opacity=round(lead.opacity, 3),
            letter_spacing_pt=letter_spacing, rotation_deg=rotation,
            ascender=round(lead.ascender, 4), descender=round(lead.descender, 4),
            space_width_pt=round(lead.space_width, 3),
        )
        z_index = min(s.seqno for s in run.spans)
        object_id = _stable_id(page_uuid, "text", z_index, text, round(first.origin[0], 1), round(first.origin[1], 1))
        objects.append(SceneObject(
            id=object_id, type=ObjectType.TEXT_NATIVE, source=ObjectSource.PDF_NATIVE,
            bbox=quad_bbox(run_quad), quad=run_quad,
            transform=[round(pdf_dir[0] * size, 4), round(pdf_dir[1] * size, 4),
                       round(-pdf_dir[1] * size, 4), round(pdf_dir[0] * size, 4), *origin_pdf],
            z_index=z_index, confidence=1.0, style=style.model_dump(),
            content={"text": text, "glyphs": glyphs, "baseline_origin": list(origin_pdf),
                     "advance_pt": round(width, 3)},
            native_ref={"spans": native_spans, "font_xref": font.get("xref"),
                        "origin": [round(first.origin[0], 4), round(first.origin[1], 4)],
                        "dir": [round(direction[0], 6), round(direction[1], 6)],
                        "gids": [c.gid for c in chars]},
            logical_group_id=_stable_id(page_uuid, "line", run.line_key),
            editable=lead.kind in (_FILL, _STROKE),
        ))
    _alignment(objects)
    return objects


def _image_objects(page: fitz.Page, space: PageSpace, page_uuid: str) -> list[SceneObject]:
    objects = []
    for ordinal, info in enumerate(page.get_image_info(xrefs=True)):
        bbox = space.rect(info["bbox"])
        if bbox[2] - bbox[0] <= 0 or bbox[3] - bbox[1] <= 0:
            continue
        objects.append(SceneObject(
            id=_stable_id(page_uuid, "image", ordinal, info.get("digest", b"").hex() if isinstance(info.get("digest"), bytes) else "", bbox),
            type=ObjectType.IMAGE, source=ObjectSource.PDF_NATIVE, bbox=bbox,
            transform=[round(v, 4) for v in info.get("transform", (1, 0, 0, 1, 0, 0))],
            z_index=int(info.get("number", ordinal)),
            content={"pixel_width": info.get("width"), "pixel_height": info.get("height"),
                     "colorspace": info.get("cs-name"), "bpc": info.get("bpc")},
            native_ref={"xref": info.get("xref"), "number": info.get("number")},
            editable=False,
        ))
    return objects


def _path_objects(page: fitz.Page, space: PageSpace, page_uuid: str) -> list[SceneObject]:
    objects = []
    try:
        clusters = page.cluster_drawings()
    except Exception:  # malformed vector content must not break analysis
        clusters = []
    for ordinal, rect in enumerate(clusters[:2000]):
        bbox = space.rect(rect)
        objects.append(SceneObject(
            id=_stable_id(page_uuid, "path", ordinal, bbox), type=ObjectType.PATH,
            source=ObjectSource.PDF_NATIVE, bbox=bbox, z_index=0, editable=False,
        ))
    return objects


def _annotation_objects(page: fitz.Page, space: PageSpace, page_uuid: str) -> list[SceneObject]:
    objects = []
    for annot in page.annots() or []:
        subtype = annot.type[1]
        kind = {
            "Ink": ObjectType.INK_ANNOTATION, "Highlight": ObjectType.ANNOTATION_HIGHLIGHT,
            "Text": ObjectType.ANNOTATION_TEXT, "FreeText": ObjectType.ANNOTATION_TEXT,
            "Redact": ObjectType.REDACTION,
        }.get(subtype, ObjectType.UNKNOWN)
        content: dict = {"subtype": subtype, "contents": annot.info.get("content", "")}
        if kind == ObjectType.INK_ANNOTATION:
            content["strokes"] = [[list(space.point(*p)) for p in stroke] for stroke in (annot.vertices or [])]
            content["width"] = annot.border.get("width")
            content["color"] = annot.colors.get("stroke")
            content["opacity"] = annot.opacity
        objects.append(SceneObject(
            id=_stable_id(page_uuid, "annot", annot.xref), type=kind,
            source=ObjectSource.ANNOTATION_NATIVE, bbox=space.rect(annot.rect), z_index=100000 + annot.xref,
            content=content, native_ref={"xref": annot.xref}, editable=False,
        ))
    for ordinal, link in enumerate(page.get_links()):
        objects.append(SceneObject(
            id=_stable_id(page_uuid, "link", ordinal, link.get("uri") or link.get("page")),
            type=ObjectType.LINK, source=ObjectSource.PDF_NATIVE, bbox=space.rect(link["from"]),
            z_index=200000 + ordinal,
            content={"uri": link.get("uri"), "page": link.get("page"), "kind": link.get("kind")},
            editable=False,
        ))
    return objects


def _classify(page_area: float, objects: list[SceneObject]) -> PageType:
    visible_chars = sum(len(o.content.get("text", "")) for o in objects
                        if o.type == ObjectType.TEXT_NATIVE and o.style.get("render_mode") != "invisible")
    images = [o.bbox for o in objects if o.type == ObjectType.IMAGE]
    coverage = 0.0
    if images:
        coverage = min(1.0, max((r[2] - r[0]) * (r[3] - r[1]) for r in images) / page_area)
    if visible_chars >= 20 and coverage < 0.5:
        return PageType.NATIVE_TEXT
    if coverage >= 0.9 and visible_chars < 20:
        return PageType.RASTER_SCAN
    if visible_chars and coverage >= 0.5:
        return PageType.MIXED
    if visible_chars:
        return PageType.NATIVE_TEXT
    return PageType.RASTER_SCAN if coverage > 0.3 else PageType.EMPTY


def analyze_page(document: fitz.Document, page_index: int, page_uuid: str) -> PageScene:
    page = document[page_index]
    rotation = page.rotation
    with unrotated(page):
        space = PageSpace(page)
        objects = (_text_objects(page, space, page_uuid) + _image_objects(page, space, page_uuid)
                   + _path_objects(page, space, page_uuid) + _annotation_objects(page, space, page_uuid))
        view_box = space.rect(page.rect)
        width, height = page.rect.width, page.rect.height
    return PageScene(
        page_index=page_index, width_pt=round(width, 3), height_pt=round(height, 3), rotation=rotation,
        view_box=view_box, page_type=_classify(max(1.0, width * height), objects), objects=objects,
    )
