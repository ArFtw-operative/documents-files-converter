import difflib
import hashlib
import json
from pathlib import Path

import fitz
from PIL import Image, ImageChops


def _normalized(value: str, ignore_whitespace: bool) -> str:
    return " ".join(value.split()) if ignore_whitespace else value


def _page_text(page: fitz.Page, options: dict) -> str:
    if not options.get("ignore_headers_footers"):
        return _normalized(page.get_text("text"), options.get("ignore_whitespace", True))
    top, bottom = page.rect.height * 0.08, page.rect.height * 0.92
    words = [word[4] for word in page.get_text("words") if word[1] >= top and word[3] <= bottom]
    return _normalized(" ".join(words), options.get("ignore_whitespace", True))


def _image_signatures(page: fitz.Page) -> list[dict]:
    return [{"digest": item.get("digest", b"").hex() if isinstance(item.get("digest"), bytes) else str(item.get("digest")),
             "bounds": list(item.get("bbox", ())), "width": item.get("width"), "height": item.get("height")}
            for item in page.get_image_info(hashes=True, xrefs=True)]


def _fingerprint(page: fitz.Page, options: dict) -> str:
    payload = {"text": _page_text(page, options),
               "images": [item["digest"] for item in _image_signatures(page)]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _annotation_signatures(page: fitz.Page) -> list[dict]:
    return [{"type": annot.type[1], "bounds": list(annot.rect),
             "author": (annot.info or {}).get("title") or "",
             "subject": (annot.info or {}).get("subject") or "",
             "content": (annot.info or {}).get("content") or ""}
            for annot in (page.annots() or [])]


def _form_signatures(page: fitz.Page) -> list[dict]:
    return [{"name": widget.field_name, "type": widget.field_type_string,
             "value": str(widget.field_value or ""), "bounds": list(widget.rect)}
            for widget in (page.widgets() or [])]


def _span_styles(page: fitz.Page) -> dict[str, list[dict]]:
    styles: dict[str, list[dict]] = {}
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = " ".join(span.get("text", "").split())
                if text:
                    styles.setdefault(text, []).append({"font": span.get("font"), "size": round(span.get("size", 0), 3),
                                                        "color": span.get("color"), "flags": span.get("flags"),
                                                        "bounds": list(span.get("bbox", ()))})
    return styles


def _visual_delta(before: fitz.Page, after: fitz.Page) -> dict:
    first = Image.open(bytes_io(before.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png"))).convert("RGB")
    second = Image.open(bytes_io(after.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png"))).convert("RGB")
    width, height = max(first.width, second.width), max(first.height, second.height)
    canvas_a, canvas_b = Image.new("RGB", (width, height), "white"), Image.new("RGB", (width, height), "white")
    canvas_a.paste(first, (0, 0)); canvas_b.paste(second, (0, 0))
    difference = ImageChops.difference(canvas_a, canvas_b)
    histogram = difference.convert("L").histogram()
    changed = sum(histogram[1:])
    return {"changed_pixel_ratio": round(changed / max(1, width * height), 6),
            "bounds": list(difference.getbbox()) if difference.getbbox() else None,
            "width": width, "height": height}


def bytes_io(value: bytes):
    from io import BytesIO
    return BytesIO(value)


def _add(differences: list[dict], kind: str, before_page: int | None, after_page: int | None,
         details: dict, before_bounds=None, after_bounds=None) -> None:
    payload = {"type": kind, "before_page": before_page, "after_page": after_page,
               "before_bounds": before_bounds, "after_bounds": after_bounds, "details": details}
    payload["id"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:24]
    payload["reviewed"] = False
    differences.append(payload)


def compare_pdfs(before_path: Path, after_path: Path, options: dict | None = None) -> dict:
    options = options or {}
    differences: list[dict] = []
    with fitz.open(before_path) as before, fitz.open(after_path) as after:
        before_fingerprints = [_fingerprint(page, options) for page in before]
        after_fingerprints = [_fingerprint(page, options) for page in after]
        available: dict[str, list[int]] = {}
        for index, fingerprint in enumerate(after_fingerprints):
            available.setdefault(fingerprint, []).append(index)
        pairs: list[tuple[int, int]] = []
        unmatched_before: list[int] = []
        used_after: set[int] = set()
        for before_index, fingerprint in enumerate(before_fingerprints):
            candidates = [index for index in available.get(fingerprint, []) if index not in used_after]
            if candidates:
                after_index = min(candidates, key=lambda index: abs(index - before_index))
                pairs.append((before_index, after_index)); used_after.add(after_index)
                if before_index != after_index:
                    _add(differences, "page_moved", before_index + 1, after_index + 1,
                         {"from": before_index + 1, "to": after_index + 1})
            else:
                unmatched_before.append(before_index)
        unmatched_after = [index for index in range(after.page_count) if index not in used_after]
        while unmatched_before and unmatched_after:
            before_index = unmatched_before.pop(0)
            after_index = min(unmatched_after, key=lambda index: abs(index - before_index)); unmatched_after.remove(after_index)
            pairs.append((before_index, after_index)); used_after.add(after_index)
        for index in unmatched_before:
            _add(differences, "page_deleted", index + 1, None, {"page": index + 1})
        for index in unmatched_after:
            _add(differences, "page_inserted", None, index + 1, {"page": index + 1})

        for before_index, after_index in sorted(pairs):
            first, second = before[before_index], after[after_index]
            first_text, second_text = _page_text(first, options), _page_text(second, options)
            matcher = difflib.SequenceMatcher(a=first_text.split(), b=second_text.split(), autojunk=False)
            for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
                if opcode == "equal":
                    continue
                kind = {"insert": "text_inserted", "delete": "text_deleted", "replace": "text_replaced"}[opcode]
                _add(differences, kind, before_index + 1, after_index + 1,
                     {"before": " ".join(first_text.split()[a0:a1]), "after": " ".join(second_text.split()[b0:b1])})
            first_blocks = {" ".join(block[4].split()): list(block[:4]) for block in first.get_text("blocks") if block[4].strip()}
            second_blocks = {" ".join(block[4].split()): list(block[:4]) for block in second.get_text("blocks") if block[4].strip()}
            for text in first_blocks.keys() & second_blocks.keys():
                if first_blocks[text] != second_blocks[text]:
                    _add(differences, "text_moved", before_index + 1, after_index + 1, {"text": text[:500]},
                         first_blocks[text], second_blocks[text])
            if not options.get("ignore_formatting"):
                first_styles, second_styles = _span_styles(first), _span_styles(second)
                for text in first_styles.keys() & second_styles.keys():
                    if first_styles[text] != second_styles[text]:
                        _add(differences, "style_changed", before_index + 1, after_index + 1,
                             {"text": text[:500], "before": first_styles[text], "after": second_styles[text]})
            for kind, left, right in (("image_changed", _image_signatures(first), _image_signatures(second)),
                                      ("annotation_changed", _annotation_signatures(first), _annotation_signatures(second)),
                                      ("form_field_changed", _form_signatures(first), _form_signatures(second))):
                if left != right:
                    _add(differences, kind, before_index + 1, after_index + 1, {"before": left, "after": right})
            visual = _visual_delta(first, second)
            if visual["changed_pixel_ratio"]:
                _add(differences, "visual_changed", before_index + 1, after_index + 1, visual)

        if before.metadata != after.metadata:
            _add(differences, "metadata_changed", None, None, {"before": before.metadata, "after": after.metadata})
        before_signatures = sum(1 for page in before for widget in (page.widgets() or []) if widget.field_type_string == "Signature")
        after_signatures = sum(1 for page in after for widget in (page.widgets() or []) if widget.field_type_string == "Signature")
        if before_signatures != after_signatures:
            _add(differences, "signature_changed", None, None, {"before": before_signatures, "after": after_signatures})
        counts: dict[str, int] = {}
        for difference in differences:
            counts[difference["type"]] = counts.get(difference["type"], 0) + 1
        return {"before_pages": before.page_count, "after_pages": after.page_count,
                "differences": differences, "summary": {"total": len(differences), "by_type": counts},
                "options": options, "text_aware": True, "visual_comparison": True}
