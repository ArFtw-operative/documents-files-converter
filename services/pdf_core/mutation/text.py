"""Native text replacement, insertion and removal (architecture §13, §14.1, §17.3)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf as fitz

from ..fonts.resolver import FontPlan, FontResolver, ResolvedFont
from ..geometry import PageSpace, glyph_quad, quad_bbox, unrotated
from ..scene import ObjectType, PageScene, SceneObject
from .errors import MutationError

# Preserve-box limits (§14.1). Anything beyond needs explicit confirmation.
MAX_TRACKING_FRACTION = 0.05
MIN_HORIZONTAL_SCALE = 0.90
MIN_SIZE_FACTOR = 0.90


@dataclass
class EditOutcome:
    page_index: int
    object_id: str | None
    kind: str
    new_text: str | None = None
    region: list[float] = field(default_factory=list)  # PDF space; union of old + new geometry
    new_bbox: list[float] | None = None
    warnings: list[str] = field(default_factory=list)
    substitutions: list[dict] = field(default_factory=list)
    fit: dict = field(default_factory=dict)


@dataclass
class _Placed:
    char: str
    font: ResolvedFont | None
    offset: float
    emit: bool


def _rgb(components: list[float], hex_value: str | None) -> tuple[tuple[float, float, float], bool]:
    """TextWriter colours are RGB. Returns (rgb, exact)."""
    if len(components) == 3:
        return (components[0], components[1], components[2]), True
    if len(components) == 1:
        return (components[0],) * 3, True
    if hex_value and len(hex_value) == 7:
        return tuple(int(hex_value[i:i + 2], 16) / 255 for i in (1, 3, 5)), False  # type: ignore[return-value]
    return (0.0, 0.0, 0.0), False


def _layout(plan: FontPlan, size: float, tracking: float, space_width: float) -> tuple[list[_Placed], float]:
    placed: list[_Placed] = []
    x = 0.0
    last = len(plan.chars) - 1
    for index, (char, resolved) in enumerate(plan.chars):
        if char.isspace() and (resolved is None or not resolved.font.has_glyph(32)):
            placed.append(_Placed(char, None, x, False))
            advance = space_width
        else:
            assert resolved is not None
            placed.append(_Placed(char, resolved, x, True))
            advance = resolved.font.glyph_advance(ord(char)) * size
        x += advance + (tracking if index < last else 0.0)
    return placed, max(0.0, x)


def _obstacles(page: fitz.Page, space: PageSpace, scene: PageScene, target: SceneObject) -> list[list[float]]:
    rects: list[list[float]] = []
    for obj in scene.objects:
        if obj.id == target.id or obj.type in (ObjectType.PATH, ObjectType.LINK):
            continue
        if obj.type == ObjectType.TEXT_NATIVE and obj.style.get("render_mode") == "invisible":
            continue
        rects.append(obj.bbox)
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        drawings = []
    for drawing in drawings:
        for item in drawing.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                rects.append(space.rect((min(p1.x, p2.x), min(p1.y, p2.y), max(p1.x, p2.x), max(p1.y, p2.y))))
            elif item[0] == "re":
                r = item[1]
                for edge in ((r.x0, r.y0, r.x0, r.y1), (r.x1, r.y0, r.x1, r.y1)):
                    rects.append(space.rect(edge))
    return rects


def _available_width(page: fitz.Page, space: PageSpace, scene: PageScene, target: SceneObject,
                     align: str) -> float:
    """Horizontal room for the run without touching neighbours, table borders or the page edge."""
    advance = float(target.content["advance_pt"])
    if abs(target.style.get("rotation_deg", 0.0)) > 0.5:
        return advance
    x0, y0, x1, y1 = target.bbox
    size = float(target.style["size_pt"])
    band_lo, band_hi = y0 + (y1 - y0) * 0.2, y1 - (y1 - y0) * 0.2
    pad = 0.3 * size
    left_limit, right_limit = scene.view_box[0] + pad, scene.view_box[2] - pad
    for ox0, oy0, ox1, oy1 in _obstacles(page, space, scene, target):
        if oy1 < band_lo or oy0 > band_hi:
            continue
        if ox0 >= x1 - 0.01:
            right_limit = min(right_limit, ox0 - pad)
        elif ox1 <= x0 + 0.01:
            left_limit = max(left_limit, ox1 + pad)
    start = x0
    end = x0 + advance
    if align == "right":
        room = end - left_limit
    elif align == "center":
        center = (start + end) / 2
        room = 2 * min(center - left_limit, right_limit - center)
    else:
        room = right_limit - start
    return max(advance, room)


def _fit(width: float, gaps: int, size: float, available: float, allow_overflow: bool) -> dict:
    """Return tracking delta / horizontal scale / size factor so the run fits (§14.1)."""
    if width <= available + 0.01:
        return {"tracking_delta": 0.0, "hscale": 1.0, "size_factor": 1.0, "overflow": False}
    max_tighten = MAX_TRACKING_FRACTION * size * gaps
    excess = width - available
    if gaps and excess <= max_tighten:
        return {"tracking_delta": -excess / gaps, "hscale": 1.0, "size_factor": 1.0, "overflow": False}
    tightened = width - max_tighten
    hscale = available / tightened
    if hscale >= MIN_HORIZONTAL_SCALE:
        return {"tracking_delta": -max_tighten / gaps if gaps else 0.0, "hscale": round(hscale, 4),
                "size_factor": 1.0, "overflow": False}
    size_factor = available / (tightened * MIN_HORIZONTAL_SCALE)
    if size_factor >= MIN_SIZE_FACTOR:
        return {"tracking_delta": -max_tighten / gaps if gaps else 0.0, "hscale": MIN_HORIZONTAL_SCALE,
                "size_factor": round(size_factor, 4), "overflow": False}
    if not allow_overflow:
        raise MutationError("needs_confirmation", "The new text is wider than the available space.",
                            {"required_pt": round(width, 2), "available_pt": round(available, 2)})
    return {"tracking_delta": 0.0, "hscale": 1.0, "size_factor": 1.0, "overflow": True}


def remove_glyphs(page: fitz.Page, space: PageSpace, target: SceneObject) -> None:
    """Remove exactly the target's characters. Redaction rectangles cover only the centre of
    each glyph cell so adjacent characters (kerned or tightly set) survive. Real space glyphs are
    removed too, otherwise they linger as an invisible run that confuses later analysis."""
    rects: list[fitz.Rect] = []
    for glyph in target.content.get("glyphs", []):
        if glyph.get("synthetic"):
            continue
        box = space.pdf_rect_to_mupdf(quad_bbox(glyph["quad"]))
        cx, cy = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
        hw = max(0.15, min(box.width * 0.3, 2.0))
        hh = max(0.3, box.height * 0.2)
        rects.append(fitz.Rect(cx - hw, cy - hh, cx + hw, cy + hh))
    if not rects:
        return
    for rect in rects:
        page.add_redact_annot(rect, fill=False, cross_out=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)


def _write(page: fitz.Page, placed: list[_Placed], origin_pdf: tuple[float, float],
           direction_pdf: tuple[float, float], size: float, hscale: float,
           color: tuple[float, float, float], opacity: float, render_mode: int) -> None:
    """Write glyphs on a baseline starting at ``origin_pdf`` (PDF user space).

    Glyphs are laid out in a local frame (baseline on y=0) and placed with one explicit matrix.
    TextWriter prepends ``1 0 0 1 cropbox_position.x cropbox_position.y+mediabox.y0 cm`` on pages
    with a crop offset, which mixes top-left and bottom-left conventions; the matrix undoes that
    translation so placement is exact for any crop box. Must be called on an unrotated page.
    """
    rect = page.rect
    writer = fitz.TextWriter(rect)
    for item in placed:
        if item.emit and item.font is not None:
            # (x, rect.height) maps to (x, 0) through TextWriter's internal y-flip.
            writer.append((item.offset, rect.height), item.char, font=item.font.font, fontsize=size)
    if not writer.text_rect or writer.text_rect.is_empty:
        return
    crop, media = page.cropbox_position, page.mediabox
    writer_shift = fitz.Matrix(1, 0, 0, 1, crop.x, crop.y + media.y0) if (bool(crop) or media.y0 != 0) \
        else fitz.Identity
    cx, sx = direction_pdf
    matrix = (fitz.Matrix(hscale, 0, 0, 1, 0, 0)
              * fitz.Matrix(cx, sx, -sx, cx, origin_pdf[0], origin_pdf[1])
              * ~writer_shift)
    writer.write_text(page, color=color, opacity=opacity if opacity < 1 else -1,
                      matrix=matrix, render_mode=render_mode)


_RENDER_MODE = {"fill": 0, "stroke": 1, "fill_stroke": 2, "invisible": 3}


def replace_text(document: fitz.Document, resolver: FontResolver, scene: PageScene,
                 target: SceneObject, payload: dict) -> EditOutcome:
    if target.type != ObjectType.TEXT_NATIVE or not target.editable:
        raise MutationError("not_editable", "This object cannot be edited as text.")
    new_text = payload.get("new_text", payload.get("text"))
    if not isinstance(new_text, str):
        raise MutationError("invalid_payload", "Replacement text is required.")
    new_text = new_text.replace("\r", "").replace("\n", " ")
    old_text = payload.get("old_text")
    if old_text is not None and old_text != target.content.get("text"):
        raise MutationError("target_modified", "The text changed since it was opened for editing.",
                            {"current_text": target.content.get("text")})
    style = target.style
    size = float(style["size_pt"])
    align = payload.get("text_align") or style.get("text_align", "left")
    page = document[scene.page_index]
    outcome = EditOutcome(scene.page_index, target.id, "replace_text", new_text)
    with unrotated(page):
        space = PageSpace(page)
        plan = resolver.plan(new_text, style, target.native_ref.get("font_xref"))
        missing = sorted({c for c, f in plan.chars if f is None and not c.isspace()})
        if missing:
            raise MutationError("font_unavailable", "No installed font can display: " + "".join(missing),
                                {"characters": missing})
        tracking = float(style.get("letter_spacing_pt") or 0.0)
        space_width = float(style.get("space_width_pt") or size * 0.25)
        placed, width = _layout(plan, size, tracking, space_width)
        old_advance = float(target.content["advance_pt"])
        if payload.get("reflow", "preserve_box") == "preserve_box":
            available = _available_width(page, space, scene, target, align)
            fit = _fit(width, max(0, len(placed) - 1), size, available, bool(payload.get("allow_overflow")))
        else:
            fit = {"tracking_delta": 0.0, "hscale": 1.0, "size_factor": 1.0, "overflow": False}
        if fit["tracking_delta"] or fit["size_factor"] != 1.0:
            size_eff = size * fit["size_factor"]
            placed, width = _layout(plan, size_eff, (tracking + fit["tracking_delta"]) * fit["size_factor"],
                                    space_width * fit["size_factor"])
        else:
            size_eff = size
        final_width = width * fit["hscale"]
        shift = {"right": old_advance - final_width, "center": (old_advance - final_width) / 2}.get(align, 0.0)
        ox, oy = target.native_ref["origin"]
        dx, dy = target.native_ref["dir"]
        origin = fitz.Point(ox + dx * shift, oy + dy * shift)

        remove_glyphs(page, space, target)
        rgb, exact = _rgb(style.get("fill_components") or [], style.get("fill") or style.get("stroke"))
        if not exact:
            outcome.warnings.append("color_converted_to_rgb")
        _write(page, placed, space.point(origin.x, origin.y), (dx, -dy), size_eff, fit["hscale"], rgb,
               float(style.get("opacity", 1.0)), _RENDER_MODE.get(style.get("render_mode", "fill"), 0))

        ascent = float(style.get("ascender", 0.9)) * size_eff
        descent = float(style.get("descender", -0.2)) * size_eff
        new_quad = space.quad(glyph_quad((origin.x, origin.y), (dx, dy), final_width, ascent, descent))
    outcome.new_bbox = quad_bbox(new_quad)
    old = target.bbox
    outcome.region = [min(old[0], outcome.new_bbox[0]), min(old[1], outcome.new_bbox[1]),
                      max(old[2], outcome.new_bbox[2]), max(old[3], outcome.new_bbox[3])]
    outcome.fit = {**fit, "align": align, "size_pt": round(size_eff, 3)}
    outcome.substitutions = [s.__dict__ for s in plan.substitutions]
    if any(s.reason != "same_family_installed" for s in plan.substitutions):
        outcome.warnings.append("font_substituted")
    if fit["hscale"] < 1 or fit["size_factor"] < 1:
        outcome.warnings.append("text_adjusted_to_fit")
    return outcome


def delete_text(document: fitz.Document, scene: PageScene, target: SceneObject) -> EditOutcome:
    if target.type != ObjectType.TEXT_NATIVE or not target.editable:
        raise MutationError("not_editable", "This object cannot be deleted as text.")
    page = document[scene.page_index]
    with unrotated(page):
        remove_glyphs(page, PageSpace(page), target)
    return EditOutcome(scene.page_index, target.id, "delete_object", region=list(target.bbox))


def add_text(document: fitz.Document, resolver: FontResolver, page_index: int, payload: dict) -> EditOutcome:
    text = payload.get("text")
    position = payload.get("position")
    if not isinstance(text, str) or not text.strip() or not position or len(position) != 2:
        raise MutationError("invalid_payload", "Text and a position are required.")
    text = text.replace("\r", "").replace("\n", " ")
    style = payload.get("style") or {}
    size = float(style.get("size_pt") or 12)
    if not 1 <= size <= 400:
        raise MutationError("invalid_payload", "Font size must be between 1 and 400 pt.")
    family = style.get("font_family") or "Liberation Sans"
    bold, italic = bool(style.get("bold")), bool(style.get("italic"))
    page = document[page_index]
    outcome = EditOutcome(page_index, None, "add_text", text)
    with unrotated(page):
        space = PageSpace(page)
        chars = []
        for char in text:
            resolved = resolver.system(family, bold, italic, bool(style.get("serif")), bool(style.get("mono")), char)
            if resolved is None and not char.isspace():
                raise MutationError("font_unavailable", f"No installed font can display {char!r}.")
            chars.append((char, resolved))
        placed, width = _layout(FontPlan(chars), size, float(style.get("letter_spacing_pt") or 0), size * 0.25)
        origin = space.pdf_point_to_mupdf(float(position[0]), float(position[1]))
        color = style.get("fill") or "#000000"
        if not (isinstance(color, str) and len(color) == 7 and color.startswith("#")):
            raise MutationError("invalid_payload", "Text colour must be #rrggbb.")
        rgb = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
        _write(page, placed, (float(position[0]), float(position[1])), (1.0, 0.0), size, 1.0, rgb,
               float(style.get("opacity") or 1.0), 0)
        quad = space.quad(glyph_quad((origin.x, origin.y), (1.0, 0.0), width, size * 0.9, size * -0.22))
    outcome.new_bbox = quad_bbox(quad)
    outcome.region = list(outcome.new_bbox)
    return outcome
