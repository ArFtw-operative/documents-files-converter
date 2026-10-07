import hashlib
import uuid
from pathlib import Path

import fitz


def _json_value(value):
    if isinstance(value, (fitz.Rect, fitz.IRect, fitz.Quad, fitz.Matrix, fitz.Point)):
        return list(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _stable_id(session_id: str, page: int, kind: str, ordinal: int, signature: str) -> str:
    try:
        namespace = uuid.UUID(session_id)
    except ValueError:
        namespace = uuid.NAMESPACE_URL
    digest = hashlib.sha256(signature.encode("utf-8", errors="replace")).hexdigest()[:24]
    # Page numbers and visual bounds are deliberately excluded from the UUID
    # name. Reorder, resize, crop, and rotation must not change object identity.
    return str(uuid.uuid5(namespace, f"{kind}:{ordinal}:{digest}"))


def _font_catalog(page: fitz.Page) -> list[dict]:
    fonts = []
    for item in page.get_fonts(full=True):
        xref, extension, subtype, base_font, resource_name, encoding, *rest = item
        fonts.append({
            "xref": xref,
            "extension": extension,
            "subtype": subtype,
            "base_font": base_font,
            "resource_name": resource_name,
            "encoding": encoding,
            "embedded": bool(xref and extension),
            "subset": "+" in base_font,
            "referencer": rest[0] if rest else None,
        })
    return fonts


def interpret_document(path: Path) -> dict:
    with fitz.open(path) as document:
        if document.needs_pass:
            raise ValueError("This PDF is encrypted. Unlock it before opening an edit session.")
        attachments = []
        for name in document.embfile_names():
            info = document.embfile_info(name)
            attachments.append({"name": name, **_json_value(info)})
        optional_content = []
        try:
            optional_content = [
                {"xref": int(xref), **_json_value(properties)}
                for xref, properties in document.get_ocgs().items()
            ]
        except Exception:
            optional_content = []
        pages = []
        for page in document:
            pages.append({
                "page": page.number + 1,
                "rotation": page.rotation,
                "boxes": {
                    "media": list(page.mediabox),
                    "crop": list(page.cropbox),
                    "bleed": list(page.bleedbox),
                    "trim": list(page.trimbox),
                    "art": list(page.artbox),
                },
                "content_streams": list(page.get_contents()),
                "font_count": len(page.get_fonts(full=True)),
                "image_count": len(page.get_images(full=True)),
                "annotation_count": sum(1 for _ in (page.annots() or [])),
                "form_field_count": sum(1 for _ in (page.widgets() or [])),
                "link_count": len(page.get_links()),
            })
        return {
            "format": document.metadata.get("format"),
            "metadata": document.metadata,
            "page_count": document.page_count,
            "permissions": int(document.permissions),
            "is_encrypted": document.is_encrypted,
            "is_repaired": document.is_repaired,
            "bookmarks": document.get_toc(simple=False),
            "attachments": attachments,
            "optional_content_groups": optional_content,
            "pages": pages,
        }


def build_page_scene(path: Path, session_id: str, page_number: int) -> dict:
    with fitz.open(path) as document:
        if document.needs_pass:
            raise ValueError("This PDF is encrypted. Unlock it before editing.")
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("The requested PDF page does not exist.")
        page = document[page_number - 1]
        content_streams = list(page.get_contents())
        fonts = _font_catalog(page)
        font_by_name = {font["base_font"]: font for font in fonts}
        objects: list[dict] = []

        raw = page.get_text("rawdict", flags=fitz.TEXTFLAGS_RAWDICT)
        text_ordinal = 0
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = [{
                        "unicode": char.get("c", ""),
                        "origin": _json_value(char.get("origin")),
                        "bbox": _json_value(char.get("bbox")),
                    } for char in span.get("chars", [])]
                    text = "".join(char["unicode"] for char in chars)
                    if not text:
                        continue
                    text_ordinal += 1
                    font = font_by_name.get(span.get("font"), {})
                    level = "Editable with reconstruction" if font.get("subset") else "Fully editable"
                    if font.get("subtype") == "Type3":
                        level = "Protected"
                    signature = f"{page.xref}:{font.get('resource_name')}:{text_ordinal}"
                    objects.append({
                        "id": _stable_id(session_id, page_number, "text", text_ordinal, signature),
                        "type": "text_run",
                        "page": page_number,
                        "bounds": _json_value(span.get("bbox")),
                        "transform": [1, 0, 0, 1, *_json_value(span.get("origin"))],
                        "z_order": len(objects),
                        "opacity": float(span.get("alpha", 255)) / 255,
                        "blend_mode": "Normal",
                        "clipping": None,
                        "source": {"content_streams": content_streams, "font_xref": font.get("xref")},
                        "editability": level,
                        "lock_state": level == "Protected",
                        "visibility": True,
                        "parent_group": None,
                        "appearance_state": "normal",
                        "text": text,
                        "characters": chars,
                        "style": {
                            "font": span.get("font"),
                            "font_size": span.get("size"),
                            "flags": span.get("flags"),
                            "color": f"#{int(span.get('color', 0)) & 0xFFFFFF:06x}",
                            "ascender": span.get("ascender"),
                            "descender": span.get("descender"),
                            "direction": _json_value(line.get("dir")),
                            "writing_mode": line.get("wmode"),
                            "embedded": font.get("embedded"),
                            "subset": font.get("subset"),
                            "font_subtype": font.get("subtype"),
                            "encoding": font.get("encoding"),
                            "font_xref": font.get("xref"),
                            "font_resource": font.get("resource_name"),
                        },
                    })

        for ordinal, image in enumerate(page.get_image_info(hashes=True, xrefs=True), 1):
            signature = f"{page.xref}:{image.get('xref')}:{_json_value(image.get('digest'))}:{ordinal}"
            image_editable = bool(image.get("xref"))
            objects.append({
                "id": _stable_id(session_id, page_number, "image", ordinal, signature),
                "type": "image",
                "page": page_number,
                "bounds": _json_value(image.get("bbox")),
                "transform": _json_value(image.get("transform")),
                "z_order": len(objects),
                "opacity": 1,
                "blend_mode": "Normal",
                "clipping": None,
                "source": {"xref": image.get("xref"), "content_streams": content_streams,
                           "digest": _json_value(image.get("digest"))},
                "editability": "Editable with reconstruction" if image_editable else "Protected",
                "lock_state": not image_editable,
                "visibility": True,
                "parent_group": None,
                "appearance_state": "normal",
                "properties": _json_value(image),
            })

        for ordinal, drawing in enumerate(page.get_drawings(extended=True), 1):
            signature = f"{page.xref}:{ordinal}"
            operators = {item[0] for item in drawing.get("items", []) if item}
            vector_editable = (drawing.get("type") in {"f", "s", "fs"}
                               and bool(operators) and operators <= {"l", "c", "qu", "re"}
                               and not drawing.get("scissor"))
            objects.append({
                "id": _stable_id(session_id, page_number, "vector", ordinal, signature),
                "type": "vector_path",
                "page": page_number,
                "bounds": _json_value(drawing.get("rect")),
                "transform": [1, 0, 0, 1, 0, 0],
                "z_order": int(drawing.get("seqno", len(objects))),
                "opacity": drawing.get("fill_opacity", drawing.get("stroke_opacity", 1)),
                "blend_mode": "Normal",
                "clipping": _json_value(drawing.get("scissor")),
                "source": {"content_streams": content_streams},
                "editability": "Editable with reconstruction" if vector_editable else "Protected",
                "lock_state": not vector_editable,
                "visibility": True,
                "parent_group": drawing.get("level"),
                "appearance_state": "normal",
                "properties": _json_value(drawing),
            })

        for ordinal, annotation in enumerate(page.annots() or [], 1):
            info = annotation.info or {}
            signature = f"{annotation.xref}:{annotation.type}"
            objects.append({
                "id": _stable_id(session_id, page_number, "annotation", ordinal, signature),
                "type": "annotation",
                "page": page_number,
                "bounds": list(annotation.rect),
                "transform": [1, 0, 0, 1, 0, 0],
                "z_order": len(objects),
                "opacity": annotation.opacity,
                "blend_mode": annotation.blendmode,
                "clipping": None,
                "source": {"xref": annotation.xref},
                "editability": "Fully editable",
                "lock_state": bool(annotation.flags & fitz.PDF_ANNOT_IS_LOCKED),
                "visibility": not bool(annotation.flags & fitz.PDF_ANNOT_IS_HIDDEN),
                "parent_group": None,
                "appearance_state": annotation.type[1],
                "properties": {"type": annotation.type[1], "flags": annotation.flags, "info": info,
                               "colors": annotation.colors, "border": annotation.border},
            })

        for ordinal, widget in enumerate(page.widgets() or [], 1):
            signature = f"{widget.xref}:{widget.field_name}:{widget.field_type}"
            objects.append({
                "id": _stable_id(session_id, page_number, "field", ordinal, signature),
                "type": "form_field",
                "page": page_number,
                "bounds": list(widget.rect),
                "transform": [1, 0, 0, 1, 0, 0],
                "z_order": len(objects),
                "opacity": 1,
                "blend_mode": "Normal",
                "clipping": None,
                "source": {"xref": widget.xref},
                "editability": "Fully editable",
                "lock_state": bool(widget.field_flags & fitz.PDF_FIELD_IS_READ_ONLY),
                "visibility": True,
                "parent_group": None,
                "appearance_state": widget.field_value,
                "properties": {
                    "name": widget.field_name, "label": widget.field_label,
                    "type": widget.field_type_string, "value": widget.field_value,
                    "flags": widget.field_flags, "font": widget.text_font,
                    "font_size": widget.text_fontsize, "text_color": widget.text_color,
                    "fill_color": widget.fill_color, "border_color": widget.border_color,
                },
            })

        for ordinal, link in enumerate(page.get_links(), 1):
            signature = f"{page.xref}:{link.get('xref')}:{ordinal}:{link.get('kind')}:{link.get('uri')}:{link.get('page')}"
            objects.append({
                "id": _stable_id(session_id, page_number, "link", ordinal, signature),
                "type": "link",
                "page": page_number,
                "bounds": _json_value(link.get("from")),
                "transform": [1, 0, 0, 1, 0, 0],
                "z_order": len(objects),
                "opacity": 1,
                "blend_mode": "Normal",
                "clipping": None,
                "source": {"xref": link.get("xref")},
                "editability": "Fully editable",
                "lock_state": False,
                "visibility": True,
                "parent_group": None,
                "appearance_state": "normal",
                "properties": _json_value(link),
            })

        try:
            # PyMuPDF 1.25.5 leaks its native page handle on Windows when the
            # experimental layers=True callback fails. The standard paint log
            # is stable and still provides authoritative cross-type z-order.
            paint_order = [{"kind": item[0], "bounds": list(item[1]), "layer": None}
                           for item in page.get_bboxlog()]
        except Exception:
            paint_order = []
        return {
            "session_id": session_id,
            "page": page_number,
            "revision": 0,
            "boxes": {"media": list(page.mediabox), "crop": list(page.cropbox),
                      "bleed": list(page.bleedbox), "trim": list(page.trimbox), "art": list(page.artbox)},
            "rotation": page.rotation,
            "content_streams": content_streams,
            "fonts": fonts,
            "paint_order": paint_order,
            "objects": objects,
            "object_counts": {kind: sum(1 for item in objects if item["type"] == kind)
                              for kind in {item["type"] for item in objects}},
        }
