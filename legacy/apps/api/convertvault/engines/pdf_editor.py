import re
import shutil
import subprocess
import hashlib
import io
import math
from pathlib import Path
from urllib.parse import urlparse

import fitz
from PIL import Image
from pypdf import PdfReader

from .base import Capability, ConversionContext


class PdfEditorEngine:
    engine_id = "pymupdf-editor"
    display_name = "ConvertVault PDF Studio"

    def available(self) -> bool:
        return True

    def version(self) -> str:
        return fitz.VersionBind

    def capabilities(self) -> list[Capability]:
        return [Capability(
            "pdf.edit", ["pdf"], ["pdf"], self.engine_id, approximate=True,
            options={"operations": {"type": "array", "maximum_items": 5000}},
            limitations=[
                "Direct replacement of subset-font or outlined text is reconstructed using an available font.",
                "Signed PDFs lose signature validity when their bytes are modified; the original remains preserved.",
            ],
        )]

    def convert(self, context: ConversionContext) -> list[Path]:
        with fitz.open(context.source) as document:
            if document.needs_pass:
                raise ValueError("The PDF is password-protected; unlock it before editing")
            additional_files = context.options.get("_additional_file_map", {})
            operations = context.options.get("operations", [])
            for operation in (item for item in operations if not item["kind"].startswith("bookmark.")):
                self._apply(document, operation, additional_files)
            self._bookmark_batch(document, [item for item in operations if item["kind"].startswith("bookmark.")])
            metadata = document.metadata or {}
            metadata["producer"] = "ConvertVault PDF Studio"
            document.set_metadata(metadata)
            document.save(context.destination, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True,
                          clean=True, use_objstms=1)
        with fitz.open(context.destination) as check:
            if check.page_count < 1: raise RuntimeError("Edited PDF validation failed: no pages remain")
        return [context.destination]

    def _apply(self, document: fitz.Document, operation: dict, files: dict[str, str]) -> None:
        kind = operation["kind"]
        if kind == "page.reorder":
            order = [int(page) - 1 for page in operation["order"]]
            if sorted(order) != list(range(document.page_count)):
                raise ValueError("Page reorder must contain every page exactly once")
            document.select(order); return
        if kind == "page.delete":
            indexes = sorted({self._page_index(document, page) for page in operation["pages"]}, reverse=True)
            if len(indexes) >= document.page_count: raise ValueError("A PDF editor project must retain at least one page")
            for index in indexes: document.delete_page(index)
            return
        if kind == "page.insert_blank":
            position = min(document.page_count, max(0, int(operation.get("page", document.page_count + 1)) - 1))
            document.new_page(pno=position, width=float(operation.get("page_width") or 595),
                              height=float(operation.get("page_height") or 842)); return
        if kind in {"page.insert_from_pdf", "page.replace_from_pdf"}:
            source_path = files.get(operation["source_file_id"])
            if not source_path or not Path(source_path).is_file():
                raise ValueError("The source PDF used for page import is unavailable")
            with fitz.open(source_path) as external:
                if external.needs_pass:
                    raise ValueError("The source PDF used for page import is password-protected")
                source_index = int(operation["source_page"]) - 1
                if source_index < 0 or source_index >= external.page_count:
                    raise ValueError("The selected source PDF page does not exist")
                target_index = int(operation["page"]) - 1
                maximum = document.page_count if kind == "page.insert_from_pdf" else document.page_count - 1
                if target_index < 0 or target_index > maximum:
                    raise ValueError("The destination page position does not exist")
                document.insert_pdf(external, from_page=source_index, to_page=source_index,
                                    start_at=target_index, links=True, annots=True, widgets=True)
                if kind == "page.replace_from_pdf":
                    document.delete_page(target_index + 1)
            return
        if kind == "metadata.set":
            allowed = {"title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate", "trapped"}
            metadata = document.metadata or {}; metadata.update({key: str(value) for key, value in operation.get("metadata", {}).items() if key in allowed})
            document.set_metadata(metadata); return
        if kind in {"watermark.text", "header_footer"}:
            for page in document:
                if kind == "watermark.text":
                    page.insert_textbox(page.rect, operation["text"], fontsize=float(operation.get("font_size", 42)),
                                        fontname="helv", color=color(operation.get("color", "#777777")), align=1,
                                        rotate=normalize_rotation(operation.get("rotation", 0)),
                                        fill_opacity=float(operation.get("opacity", 0.25)), overlay=True)
                else:
                    rect = fitz.Rect(24, page.rect.height - 28, page.rect.width - 24, page.rect.height - 10)
                    page.insert_textbox(rect, operation["text"].replace("{page}", str(page.number + 1)),
                                        fontsize=float(operation.get("font_size", 9)), fontname="helv",
                                        color=color(operation.get("color", "#444444")), align=1)
            return
        if kind == "form.import_data":
            values = operation.get("metadata", {})
            for form_page in document:
                for widget in form_page.widgets() or []:
                    if widget.field_name in values:
                        widget.field_value = str(values[widget.field_name])
                        widget.update()
            return
        if kind == "form.reset":
            for form_page in document:
                for widget in form_page.widgets() or []:
                    widget.reset()
                    widget.update()
            return
        if kind == "form.flatten" and not operation.get("page"):
            document.bake(annots=False, widgets=True)
            return
        if kind == "redact.search":
            self._search_redact(document, operation)
            return
        if kind.startswith("attachment."):
            name = operation.get("attachment_name")
            if kind == "attachment.delete":
                if name not in document.embfile_names(): raise ValueError("The embedded attachment no longer exists")
                document.embfile_del(name); return
            asset_path = files.get(operation["attachment_file_id"])
            if not asset_path or not Path(asset_path).is_file(): raise ValueError("The embedded attachment asset is unavailable")
            filename = safe_attachment_name(name or Path(asset_path).name)
            if kind == "attachment.replace":
                if name not in document.embfile_names(): raise ValueError("The embedded attachment no longer exists")
                # PyMuPDF 1.25.5 mistakenly reads ``m_internal`` from its
                # Python input after converting it. A tagged BytesIO satisfies
                # that wrapper contract while preserving the existing name-tree
                # object and avoiding delete/re-add xref corruption.
                payload = io.BytesIO(Path(asset_path).read_bytes()); payload.m_internal = True
                document.embfile_upd(name, payload, filename=filename,
                                     ufilename=filename, desc=operation.get("text") or filename)
            else:
                if filename in document.embfile_names(): raise ValueError("An embedded attachment with this name already exists")
                document.embfile_add(filename, Path(asset_path).read_bytes(), filename=filename,
                                     ufilename=filename, desc=operation.get("text") or filename)
            return
        if kind.startswith("bookmark."):
            toc = document.get_toc(simple=False)
            index = operation.get("bookmark_index")
            if kind == "bookmark.delete":
                if index is None or index >= len(toc): raise ValueError("The bookmark no longer exists")
                level = toc[index][0]; end = index + 1
                while end < len(toc) and toc[end][0] > level: end += 1
                del toc[index:end]
            else:
                item = [int(operation.get("bookmark_level") or 1), operation["bookmark_title"],
                        int(operation["target_page"])]
                if item[2] > document.page_count: raise ValueError("The bookmark destination page does not exist")
                if kind == "bookmark.update":
                    if index is None or index >= len(toc): raise ValueError("The bookmark no longer exists")
                    toc[index][:3] = item
                else:
                    position = len(toc) if index is None else min(index, len(toc))
                    previous_level = toc[position - 1][0] if position else 0
                    item[0] = min(item[0], previous_level + 1)
                    toc.insert(position, item)
            document.set_toc(toc, collapse=0)
            return
        page = document[self._page_index(document, operation.get("page"))]
        rectangle = fitz.Rect(operation["rect"]) if operation.get("rect") else None
        if rectangle and not page.rect.intersects(rectangle): raise ValueError("An edit rectangle falls outside its page")
        if kind == "page.rotate":
            page.set_rotation((page.rotation + normalize_rotation(operation.get("rotation", 90))) % 360)
        elif kind == "page.crop":
            if not page.mediabox.contains(rectangle): raise ValueError("Crop rectangle must stay inside the media box")
            page.set_cropbox(rectangle)
        elif kind == "page.resize":
            self._resize_page(document, page, float(operation["page_width"]),
                              float(operation["page_height"]), operation.get("resize_mode", "fit"))
        elif kind == "page.set_boxes":
            self._set_page_boxes(document, page, operation["page_boxes"])
        elif kind == "content.add_text":
            fontname, fontfile = resolve_font(str(operation.get("font", "Helvetica")))
            remaining = page.insert_textbox(rectangle, operation["text"], fontname=fontname, fontfile=fontfile,
                                            fontsize=float(operation.get("font_size", 12)), color=color(operation.get("color", "#000000")),
                                            rotate=normalize_rotation(operation.get("rotation", 0)), fill_opacity=float(operation.get("opacity", 1)))
            if remaining < 0: raise ValueError("Text does not fit inside its edit box")
        elif kind in {"content.add_image", "signature.add"}:
            image_path = files.get(operation["image_file_id"])
            if not image_path or not Path(image_path).exists(): raise ValueError("The image used by this edit is unavailable")
            page.insert_image(rectangle, filename=image_path, keep_proportion=True, rotate=normalize_rotation(operation.get("rotation", 0)), overlay=True)
        elif kind == "content.add_shape":
            shape = operation.get("text", "rectangle").lower(); stroke = color(operation.get("color", "#000000")); fill = color(operation["fill"]) if operation.get("fill") else None
            arguments = {"color": stroke, "fill": fill, "width": float(operation.get("width", 1)),
                         "stroke_opacity": float(operation.get("opacity", 1)), "fill_opacity": float(operation.get("opacity", 1)), "overlay": True}
            if shape == "ellipse": page.draw_oval(rectangle, **arguments)
            elif shape == "line": page.draw_line(rectangle.tl, rectangle.br, **arguments)
            else: page.draw_rect(rectangle, **arguments)
        elif kind == "content.draw":
            points = [fitz.Point(point) for point in operation["points"]]
            page.draw_polyline(points, color=color(operation.get("color", "#000000")),
                               width=float(operation.get("width", 1)), stroke_opacity=float(operation.get("opacity", 1)), overlay=True)
        elif kind == "content.replace_text":
            matches = page.search_for(operation["text"])
            if not matches: raise ValueError("The requested text was not found on this page")
            for match in matches:
                page.add_redact_annot(match, text=operation.get("replacement", ""), fontname="helv",
                                      fontsize=float(operation.get("font_size", 11)), text_color=color(operation.get("color", "#000000")),
                                      fill=color(operation.get("fill") or "#ffffff"))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        elif kind == "content.edit_text_object":
            self._edit_text_object(page, rectangle, operation)
        elif kind in {"content.transform_image", "content.replace_image_object", "content.delete_image_object"}:
            self._edit_image_object(document, page, operation, files)
        elif kind in {"content.transform_vector", "content.delete_vector_object"}:
            self._edit_vector_object(page, operation)
        elif kind == "redact":
            page.add_redact_annot(rectangle, text=operation.get("text") or "", fontname="helv",
                                  fontsize=float(operation.get("font_size", 10)), fill=color(operation.get("fill") or "#000000"),
                                  text_color=color(operation.get("color", "#ffffff")))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        elif kind.startswith("annotate."):
            self._annotation(document, page, kind, rectangle, operation, files)
        elif kind == "link.add":
            uri = operation.get("uri")
            if uri:
                parsed = urlparse(uri)
                if parsed.scheme not in {"http", "https", "mailto"}: raise ValueError("Only HTTP(S) and mail links are allowed")
                page.insert_link({"kind": fitz.LINK_URI, "from": rectangle, "uri": uri})
            else:
                target = self._page_index(document, operation.get("target_page"))
                page.insert_link({"kind": fitz.LINK_GOTO, "from": rectangle, "page": target})
        elif kind.startswith("form."):
            self._form(document, page, kind, rectangle, operation)
        else:
            raise ValueError(f"Unsupported PDF edit operation: {kind}")

    def _form(self, document: fitz.Document, page: fitz.Page, kind: str,
              rect: fitz.Rect | None, operation: dict) -> None:
        def find_widget() -> fitz.Widget:
            source_name = operation.get("object_id") or operation.get("field_name")
            match = next((item for item in (page.widgets() or []) if item.field_name == source_name), None)
            if not match:
                raise ValueError("The selected form field no longer exists")
            return match

        if kind == "form.delete":
            page.delete_widget(find_widget())
            return
        if kind == "form.update":
            widget = find_widget()
            self._configure_widget(document, widget, operation)
            widget.update()
            return
        if kind == "form.flatten":
            widget = find_widget() if operation.get("field_name") else None
            if widget is None:
                # Page-scoped flattening is represented by selected widget names;
                # an omitted name deliberately flattens the complete AcroForm.
                document.bake(annots=False, widgets=True)
                return
            bounds = fitz.Rect(widget.rect)
            appearance = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=bounds, alpha=True).tobytes("png")
            page.delete_widget(widget)
            page.insert_image(bounds, stream=appearance, overlay=True)
            return

        widget = fitz.Widget()
        widget.field_name = operation.get("field_name") or f"field_{page.number + 1}_{len(list(page.widgets() or [])) + 1}"
        widget.rect = rect
        widget.field_type = {
            "form.text": fitz.PDF_WIDGET_TYPE_TEXT,
            "form.multiline": fitz.PDF_WIDGET_TYPE_TEXT,
            "form.checkbox": fitz.PDF_WIDGET_TYPE_CHECKBOX,
            "form.radio": fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
            "form.combo": fitz.PDF_WIDGET_TYPE_COMBOBOX,
            "form.listbox": fitz.PDF_WIDGET_TYPE_LISTBOX,
            "form.pushbutton": fitz.PDF_WIDGET_TYPE_BUTTON,
            "form.signature": fitz.PDF_WIDGET_TYPE_SIGNATURE,
            "form.date": fitz.PDF_WIDGET_TYPE_TEXT,
            "form.numeric": fitz.PDF_WIDGET_TYPE_TEXT,
        }[kind]
        if kind == "form.multiline": operation = {**operation, "multiline": True}
        if kind == "form.date": operation = {**operation, "format_type": "date"}
        if kind == "form.numeric": operation = {**operation, "format_type": "number"}
        if kind == "form.radio" and operation.get("field_value") is None:
            operation = {**operation, "field_value": "Off"}
        self._configure_widget(document, widget, operation, creating=True)
        page.add_widget(widget)
        widget = next(item for item in (page.widgets() or []) if item.field_name == widget.field_name)
        self._persist_widget_properties(document, widget, operation)

    @staticmethod
    def _configure_widget(document: fitz.Document, widget: fitz.Widget, operation: dict,
                          creating: bool = False) -> None:
        if operation.get("field_name"):
            widget.field_name = operation["field_name"]
        widget.field_label = operation.get("field_label") or widget.field_label or widget.field_name
        value = operation.get("field_value", operation.get("text"))
        if value is not None and widget.field_type != fitz.PDF_WIDGET_TYPE_SIGNATURE:
            widget.field_value = value
        widget.text_font = operation.get("font") or widget.text_font or "Helv"
        widget.text_fontsize = float(operation.get("font_size") or widget.text_fontsize or 11)
        widget.text_color = color(operation.get("color", "#000000"))
        widget.fill_color = color(operation["fill"]) if operation.get("fill") else widget.fill_color
        widget.border_color = color(operation.get("color", "#000000"))
        widget.border_width = float(operation.get("width", 1))
        widget.border_style = {"solid": "S", "dashed": "D", "beveled": "B", "inset": "I", "underline": "U"}.get(operation.get("border_style"), "S")
        widget.text_format = {"left": 0, "center": 1, "right": 2}.get(operation.get("alignment"), 0)
        widget.field_display = 1 if operation.get("hidden") else (2 if not operation.get("printable", True) else 0)
        flags = int(widget.field_flags or 0)
        flags = flags | fitz.PDF_FIELD_IS_REQUIRED if operation.get("required") else flags & ~fitz.PDF_FIELD_IS_REQUIRED
        flags = flags | fitz.PDF_FIELD_IS_READ_ONLY if operation.get("readonly") else flags & ~fitz.PDF_FIELD_IS_READ_ONLY
        if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
            flags = flags | 4096 if operation.get("multiline") else flags & ~4096
            flags = flags | 8192 if operation.get("password") else flags & ~8192
            flags = flags | 8388608 if operation.get("no_scroll") else flags & ~8388608
            flags = flags | 16777216 if operation.get("comb") else flags & ~16777216
            widget.text_maxlen = int(operation.get("max_length") or 0)
        if widget.field_type == fitz.PDF_WIDGET_TYPE_BUTTON:
            flags |= 65536
            widget.button_caption = operation.get("field_label") or operation.get("text") or widget.field_name
        widget.field_flags = flags
        if operation.get("choice_values") and widget.field_type in {
            fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX
        }:
            widget.choice_values = list(operation["choice_values"])
        if not creating:
            PdfEditorEngine._persist_widget_properties(document, widget, operation)

    @staticmethod
    def _persist_widget_properties(document: fitz.Document, widget: fitz.Widget, operation: dict) -> None:
        if operation.get("default_value") is not None:
            document.xref_set_key(widget.xref, "DV", fitz.get_pdf_str(str(operation["default_value"])))
        if operation.get("validation_pattern"):
            document.xref_set_key(widget.xref, "CVValidation", fitz.get_pdf_str(operation["validation_pattern"]))
        if operation.get("calculation"):
            document.xref_set_key(widget.xref, "CVCalculation", fitz.get_pdf_str(operation["calculation"]))
        if operation.get("format_type", "none") != "none":
            document.xref_set_key(widget.xref, "CVFormat", fitz.get_pdf_str(operation["format_type"]))
        if operation.get("export_value"):
            document.xref_set_key(widget.xref, "CVExportValue", fitz.get_pdf_str(operation["export_value"]))
        if operation.get("tab_order"):
            document.xref_set_key(widget.xref, "StructParent", str(int(operation["tab_order"]) - 1))
        if operation.get("choice_values") and widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
            choices = " ".join(fitz.get_pdf_str(str(value)) for value in operation["choice_values"])
            document.xref_set_key(widget.xref, "CVChoices", f"[{choices}]")

    @staticmethod
    def _bookmark_batch(document: fitz.Document, operations: list[dict]) -> None:
        if not operations:
            return
        toc = document.get_toc(simple=False)
        for operation in operations:
            kind = operation["kind"]; index = operation.get("bookmark_index")
            if kind == "bookmark.delete":
                if index is None or index >= len(toc): raise ValueError("The bookmark no longer exists")
                level = toc[index][0]; end = index + 1
                while end < len(toc) and toc[end][0] > level: end += 1
                del toc[index:end]; continue
            item = [int(operation.get("bookmark_level") or 1), operation["bookmark_title"],
                    int(operation["target_page"])]
            if item[2] > document.page_count: raise ValueError("The bookmark destination page does not exist")
            if kind == "bookmark.update":
                if index is None or index >= len(toc): raise ValueError("The bookmark no longer exists")
                toc[index][:3] = item
            else:
                position = len(toc) if index is None else min(index, len(toc))
                previous_level = toc[position - 1][0] if position else 0
                item[0] = min(item[0], previous_level + 1); toc.insert(position, item)
        document.set_toc(toc, collapse=0)

    @staticmethod
    def _search_redact(document: fitz.Document, operation: dict) -> None:
        patterns = [re.escape(term) for term in operation.get("search_terms", []) if term]
        pattern_type = operation.get("pattern_type")
        predefined = {
            "name": r"\b[A-Z][a-z]{1,40}\s+[A-Z][a-z]{1,40}\b",
            "email": r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            "phone": r"(?<!\w)(?:\+?\d[\d .()-]{7,}\d)(?!\w)",
            "account": r"\b(?:account\s*(?:no\.?|number)?\s*[:#-]?\s*)?[A-Z0-9-]{8,24}\b",
            "credit_card": r"\b(?:\d[ -]*?){13,19}\b",
            "national_id": r"\b[A-Z0-9]{3,6}[- ]?\d{4,12}\b",
            "ip": r"\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b",
            "date": r"\b(?:\d{1,2}[/-]){2}\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
        }
        if pattern_type == "custom_regex":
            patterns.append(operation["custom_regex"])
        elif pattern_type and pattern_type != "keyword":
            patterns.append(predefined[pattern_type])
        if operation.get("whole_word"):
            patterns = [rf"\b(?:{pattern})\b" for pattern in patterns]
        flags = 0 if operation.get("case_sensitive") else re.IGNORECASE
        compiled = [re.compile(pattern, flags) for pattern in patterns]
        selected = set(operation.get("pages") or range(1, document.page_count + 1))
        matched = 0
        for page_number in sorted(selected):
            if page_number < 1 or page_number > document.page_count:
                raise ValueError("A redaction target page does not exist")
            page = document[page_number - 1]
            text = page.get_text("text")
            values = {match.group(0) for regex in compiled for match in regex.finditer(text) if match.group(0).strip()}
            for value in values:
                for bounds in page.search_for(value):
                    page.add_redact_annot(bounds, text=operation.get("replacement") or "",
                                          fill=color(operation.get("fill") or "#000000"),
                                          text_color=color(operation.get("color") or "#ffffff"))
                    matched += 1
            if values:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                                      graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                                      text=fitz.PDF_REDACT_TEXT_REMOVE)
            if operation.get("remove_comments"):
                for annotation in list(page.annots() or []):
                    page.delete_annot(annotation)
            if operation.get("remove_form_values"):
                for widget in page.widgets() or []:
                    widget.field_value = ""; widget.update()
        if not matched:
            raise ValueError("No redaction matches were found on the selected pages")
        document.scrub(
            attached_files=bool(operation.get("remove_attachments")), clean_pages=True,
            embedded_files=bool(operation.get("remove_attachments")),
            hidden_text=bool(operation.get("remove_hidden_text", True)), javascript=True,
            metadata=bool(operation.get("remove_metadata")), redactions=True,
            redact_images=fitz.PDF_REDACT_IMAGE_PIXELS, remove_links=False,
            reset_fields=bool(operation.get("remove_form_values")),
            reset_responses=bool(operation.get("remove_comments")), thumbnails=True,
            xml_metadata=bool(operation.get("remove_metadata")),
        )

    def _annotation(self, document: fitz.Document, page: fitz.Page, kind: str,
                    rect: fitz.Rect, operation: dict, files: dict[str, str]) -> None:
        def find(name: str | None) -> fitz.Annot:
            match = None
            if name and name.startswith("xref:"):
                try:
                    wanted_xref = int(name.split(":", 1)[1])
                    match = next((item for item in (page.annots() or []) if item.xref == wanted_xref), None)
                except ValueError:
                    match = None
            if match is None:
                match = next((item for item in (page.annots() or [])
                              if (item.info or {}).get("id") == name), None)
            if not match:
                raise ValueError("The selected annotation no longer exists")
            return match

        if kind == "annotate.delete":
            page.delete_annot(find(operation.get("annotation_name")))
            return
        if kind == "annotate.update":
            self._configure_annotation(document, find(operation.get("annotation_name")), operation)
            return
        if kind == "annotate.reply":
            parent = find(operation.get("parent_annotation_name"))
            annot = page.add_text_annot(parent.rect.tl, operation.get("text", ""))
            annot.set_irt_xref(parent.xref)
            self._configure_annotation(document, annot, operation)
            return

        quads = [fitz.Quad(*([value[index:index + 2] for index in range(0, 8, 2)]
                             if len(value) == 8 else value))
                 for value in operation.get("quads", [])]
        target = quads or rect
        annot = None
        if kind == "annotate.highlight": annot = page.add_highlight_annot(target)
        elif kind == "annotate.underline": annot = page.add_underline_annot(target)
        elif kind == "annotate.squiggly": annot = page.add_squiggly_annot(target)
        elif kind == "annotate.strikeout": annot = page.add_strikeout_annot(target)
        elif kind == "annotate.comment": annot = page.add_text_annot(rect.tl, operation.get("text", ""))
        elif kind in {"annotate.free_text", "annotate.callout"}:
            callout = None
            if kind == "annotate.callout":
                points = [fitz.Point(value) for value in operation.get("points", [])]
                callout = points[:3] if len(points) >= 2 else [rect.tl, rect.bl]
            annot = page.add_freetext_annot(
                rect, operation.get("text", ""), fontsize=float(operation.get("font_size", 11)),
                text_color=color(operation.get("color", "#000000")),
                fill_color=color(operation["fill"]) if operation.get("fill") else None,
                border_color=color(operation.get("color", "#000000")),
                border_width=float(operation.get("width", 1)), callout=callout,
                line_end=_line_end(operation.get("line_end") or "open_arrow"),
                opacity=float(operation.get("opacity", 1)),
            )
        elif kind == "annotate.ink":
            annot = page.add_ink_annot([[list(map(float, value)) for value in operation["points"]]])
        elif kind in {"annotate.line", "annotate.arrow", "annotate.measurement"}:
            points = [fitz.Point(value) for value in operation.get("points", [])]
            start, end = (points[0], points[1]) if len(points) >= 2 else (rect.tl, rect.br)
            annot = page.add_line_annot(start, end)
            if kind == "annotate.arrow":
                annot.set_line_ends(_line_end(operation.get("line_start") or "none"),
                                     _line_end(operation.get("line_end") or "open_arrow"))
            if kind == "annotate.measurement":
                unit = operation.get("measurement_unit") or "pt"
                scale = float(operation.get("measurement_scale") or 1)
                ratio = fitz.get_pdf_str(f"1 pt = {scale:g} {unit}")
                document.xref_set_key(annot.xref, "IT", "/LineDimension")
                document.xref_set_key(annot.xref, "Measure",
                    f"<< /Type /Measure /Subtype /RL /R {ratio} /X [<< /U {fitz.get_pdf_str(unit)} /C {scale:g} >>] >>")
        elif kind == "annotate.rectangle": annot = page.add_rect_annot(rect)
        elif kind == "annotate.ellipse": annot = page.add_circle_annot(rect)
        elif kind == "annotate.polygon": annot = page.add_polygon_annot([fitz.Point(value) for value in operation["points"]])
        elif kind == "annotate.polyline": annot = page.add_polyline_annot([fitz.Point(value) for value in operation["points"]])
        elif kind == "annotate.stamp": annot = page.add_stamp_annot(rect, _stamp_number(operation.get("stamp_type")))
        elif kind == "annotate.attachment":
            attachment_path = files.get(operation["attachment_file_id"])
            if not attachment_path or not Path(attachment_path).is_file():
                raise ValueError("The annotation attachment file is unavailable")
            annot = page.add_file_annot(rect.tl, Path(attachment_path).read_bytes(),
                                        filename=Path(attachment_path).name,
                                        desc=operation.get("text") or "Attached file")
        elif kind == "annotate.caret": annot = page.add_caret_annot(rect.tl)
        elif kind == "annotate.replace_text":
            annot = page.add_strikeout_annot(target)
            operation = {**operation, "subject": operation.get("subject") or "Replace Text"}
        elif kind == "annotate.redaction_mark":
            annot = page.add_redact_annot(target, text=operation.get("text") or None,
                                          fill=color(operation["fill"]) if operation.get("fill") else None,
                                          text_color=color(operation.get("color", "#000000")))
        if not annot:
            raise ValueError(f"Unsupported PDF annotation operation: {kind}")
        self._configure_annotation(document, annot, operation)

    @staticmethod
    def _configure_annotation(document: fitz.Document, annot: fitz.Annot, operation: dict) -> None:
        current = annot.info or {}
        annotation_type = annot.type[1]
        annot.set_info(content=operation.get("text") if operation.get("text") is not None else current.get("content"),
                       title=operation.get("author") if operation.get("author") is not None else current.get("title"),
                       subject=operation.get("subject") if operation.get("subject") is not None else current.get("subject"),
                       modDate=fitz.get_pdf_now())
        colors = {"stroke": color(operation.get("color", "#000000"))}
        if operation.get("fill") and annotation_type in {"Square", "Circle", "Polygon", "PolyLine", "Line"}:
            colors["fill"] = color(operation["fill"])
        annot.set_colors(**colors)
        if annotation_type in {"FreeText", "Ink", "Line", "Square", "Circle", "Polygon", "PolyLine"}:
            style = {"solid": "S", "dashed": "D", "beveled": "B", "inset": "I", "underline": "U"}[operation.get("border_style", "solid")]
            annot.set_border(width=float(operation.get("width", 1)), style=style,
                             dashes=[3, 2] if style == "D" else None)
        annot.set_opacity(float(operation.get("opacity", 1)))
        flags = annot.flags
        flags = flags | fitz.PDF_ANNOT_IS_PRINT if operation.get("printable", True) else flags & ~fitz.PDF_ANNOT_IS_PRINT
        flags = flags | fitz.PDF_ANNOT_IS_LOCKED if operation.get("locked", False) else flags & ~fitz.PDF_ANNOT_IS_LOCKED
        flags = flags & ~(fitz.PDF_ANNOT_IS_HIDDEN | fitz.PDF_ANNOT_IS_NO_VIEW) if operation.get("visible", True) else flags | fitz.PDF_ANNOT_IS_HIDDEN
        annot.set_flags(flags)
        name = operation.get("annotation_name")
        if name:
            document.xref_set_key(annot.xref, "NM", fitz.get_pdf_str(name))
        status = operation.get("annotation_status", "none")
        if status != "none":
            state = {"accepted": "Accepted", "rejected": "Rejected", "cancelled": "Cancelled",
                     "completed": "Completed", "open": "Marked", "closed": "Completed"}[status]
            document.xref_set_key(annot.xref, "StateModel", "/Review")
            document.xref_set_key(annot.xref, "State", f"/{state}")
        # PyMuPDF's Redact updater assumes a simple five-line appearance when
        # cross_out=True. Replacement text produces a richer appearance stream,
        # so explicitly disable the cross-out reconstruction for these marks.
        annot.update(cross_out=False) if annotation_type == "Redact" else annot.update()

    def _edit_text_object(self, page: fitz.Page, rectangle: fitz.Rect, operation: dict) -> None:
        original = operation["text"]
        start, end = int(operation["range_start"]), int(operation["range_end"])
        if start < 0 or end < start or end > len(original):
            raise ValueError("The native text edit range no longer matches its source object")
        rebuilt = original[:start] + operation.get("replacement", "") + original[end:]
        page.add_redact_annot(rectangle, fill=False, cross_out=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_REMOVE)
        if not rebuilt:
            return
        fontname, fontfile = None, None
        resource = operation.get("font_resource")
        if resource and operation.get("font_policy") != "substitute":
            fontname = resource if str(resource).startswith("/") else f"/{resource}"
        else:
            fontname, fontfile = resolve_font(str(operation.get("font", "Helvetica")))
        arguments = {
            "fontname": fontname,
            "fontfile": fontfile,
            "fontsize": float(operation.get("font_size", 12)),
            "color": color(operation.get("color", "#000000")),
            "fill_opacity": float(operation.get("opacity", 1)),
            "overlay": True,
        }
        policy = operation.get("reflow_policy", "preserve_line_positions")
        if policy == "preserve_line_positions":
            page.insert_text(fitz.Point(operation["origin"]), rebuilt, **arguments)
            return
        edit_rect = fitz.Rect(rectangle)
        if policy == "expand_box":
            edit_rect.x1 = max(edit_rect.x1, page.rect.x1 - 12)
            edit_rect.y1 = max(edit_rect.y1, min(page.rect.y1 - 12, edit_rect.y0 + float(operation.get("font_size", 12)) * 4))
        remaining = page.insert_textbox(edit_rect, rebuilt, **arguments)
        if remaining < 0:
            raise ValueError("Edited text overflows its object bounds; choose expand-box or manual layout")

    def _edit_image_object(self, document: fitz.Document, page: fitz.Page,
                           operation: dict, files: dict[str, str]) -> None:
        source_rect = fitz.Rect(operation["source_rect"])
        image_bytes = None
        if operation["kind"] == "content.transform_image":
            digest = str(operation.get("source_digest") or "").lower()
            candidates = page.get_image_info(hashes=True, xrefs=True)
            if digest:
                candidates = [item for item in candidates
                              if _digest_hex(item.get("digest")) == digest]
            candidates = [item for item in candidates if fitz.Rect(item.get("bbox")).intersects(source_rect)]
            source_xref = int(candidates[0].get("xref")) if len(candidates) == 1 else int(operation.get("source_xref") or 0)
            if source_xref:
                try:
                    extracted = document.extract_image(source_xref)
                    image_bytes = extracted.get("image") if extracted else None
                except ValueError:
                    image_bytes = None
            if not image_bytes:
                raise ValueError("The selected image resource can no longer be resolved safely after earlier edits")
        page.add_redact_annot(source_rect, fill=False, cross_out=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE,
                              graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                              text=fitz.PDF_REDACT_TEXT_NONE)
        if operation["kind"] == "content.delete_image_object":
            return
        if operation["kind"] == "content.replace_image_object":
            replacement = files.get(operation["image_file_id"])
            if not replacement or not Path(replacement).is_file():
                raise ValueError("The replacement image used by this edit is unavailable")
            image_bytes = Path(replacement).read_bytes()
        elif not image_bytes:
            raise ValueError("The selected image resource cannot be extracted safely")
        crop_box = operation.get("crop")
        rotation = float(operation.get("rotation", 0)) % 360
        if crop_box or rotation:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                if crop_box:
                    left, top, right, bottom = crop_box
                    image = image.crop((round(left * image.width), round(top * image.height),
                                        round(right * image.width), round(bottom * image.height)))
                if rotation:
                    image = image.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                image_bytes = buffer.getvalue()
        page.insert_image(fitz.Rect(operation["rect"]), stream=image_bytes,
                          keep_proportion=False, overlay=True)

    def _edit_vector_object(self, page: fitz.Page, operation: dict) -> None:
        source_rect = fitz.Rect(operation["source_rect"])
        properties = operation["vector_properties"]
        padding = max(1.0, float(properties.get("width") or 1.0))
        removal_rect = fitz.Rect(source_rect)
        removal_rect.x0 -= padding; removal_rect.y0 -= padding
        removal_rect.x1 += padding; removal_rect.y1 += padding
        page.add_redact_annot(removal_rect, fill=False, cross_out=False)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                              graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                              text=fitz.PDF_REDACT_TEXT_NONE)
        if operation["kind"] == "content.delete_vector_object":
            return
        target_rect = fitz.Rect(operation["rect"])
        rotation = math.radians(float(operation.get("rotation", 0)))

        def point(value) -> fitz.Point:
            candidate = fitz.Point(value)
            sx = target_rect.width / source_rect.width
            sy = target_rect.height / source_rect.height
            transformed = fitz.Point(target_rect.x0 + (candidate.x - source_rect.x0) * sx,
                                     target_rect.y0 + (candidate.y - source_rect.y0) * sy)
            if not rotation:
                return transformed
            center = (target_rect.tl + target_rect.br) / 2
            dx, dy = transformed.x - center.x, transformed.y - center.y
            return fitz.Point(center.x + dx * math.cos(rotation) - dy * math.sin(rotation),
                              center.y + dx * math.sin(rotation) + dy * math.cos(rotation))

        shape = page.new_shape()
        for item in properties.get("items", []):
            operator = item[0]
            if operator == "l":
                shape.draw_line(point(item[1]), point(item[2]))
            elif operator == "c":
                shape.draw_bezier(point(item[1]), point(item[2]), point(item[3]), point(item[4]))
            elif operator == "qu":
                quad = fitz.Quad(point(item[1]), point(item[2]), point(item[3]), point(item[4]))
                shape.draw_quad(quad)
            elif operator == "re":
                rect = fitz.Rect(item[1])
                corners = [point(rect.tl), point(rect.tr), point(rect.br), point(rect.bl), point(rect.tl)]
                shape.draw_polyline(corners)
            else:
                raise ValueError(f"The selected vector path contains unsupported operator '{operator}'")
        stroke = color(operation["color"]) if operation.get("color") else properties.get("color")
        fill = color(operation["fill"]) if operation.get("fill") else properties.get("fill")
        shape.finish(
            width=float(operation.get("width") or properties.get("width") or 1),
            color=tuple(stroke) if stroke is not None else None,
            fill=tuple(fill) if fill is not None else None,
            dashes=properties.get("dashes"),
            lineCap=max(properties.get("lineCap") or (0,)),
            lineJoin=float(properties.get("lineJoin") or 0),
            closePath=bool(properties.get("closePath")),
            even_odd=bool(properties.get("even_odd")),
            stroke_opacity=float(operation.get("opacity") if operation.get("opacity") is not None
                                 else properties.get("stroke_opacity") or 1),
            fill_opacity=float(operation.get("opacity") if operation.get("opacity") is not None
                               else properties.get("fill_opacity") or 1),
        )
        shape.commit(overlay=True)

    @staticmethod
    def _set_page_boxes(document: fitz.Document, page: fitz.Page,
                        boxes: dict[str, list[float]]) -> None:
        media = fitz.Rect(boxes.get("media") or page.mediabox)
        for name, value in boxes.items():
            if name != "media" and not media.contains(fitz.Rect(value)):
                raise ValueError(f"The {name} box must stay inside the media box")
        if "media" in boxes:
            page.set_mediabox(media)
            page = document.reload_page(page)
        setters = {
            "crop": page.set_cropbox, "bleed": page.set_bleedbox,
            "trim": page.set_trimbox, "art": page.set_artbox,
        }
        for name in ("crop", "bleed", "trim", "art"):
            if name in boxes:
                setters[name](fitz.Rect(boxes[name]))

    @staticmethod
    def _resize_page(document: fitz.Document, page: fitz.Page, width: float,
                     height: float, mode: str) -> None:
        if page.rotation:
            page.remove_rotation()
            page = document.reload_page(page)
        old_media = fitz.Rect(page.mediabox)
        old_width, old_height = old_media.width, old_media.height
        if old_width <= 0 or old_height <= 0:
            raise ValueError("The page media box has invalid dimensions")
        if mode == "stretch":
            sx, sy = width / old_width, height / old_height
        else:
            scale = (min if mode == "fit" else max)(width / old_width, height / old_height)
            sx = sy = scale
        tx, ty = (width - old_width * sx) / 2, (height - old_height * sy) / 2

        def transformed(rectangle) -> fitz.Rect:
            rect = fitz.Rect(rectangle)
            return fitz.Rect(tx + (rect.x0 - old_media.x0) * sx,
                             ty + (rect.y0 - old_media.y0) * sy,
                             tx + (rect.x1 - old_media.x0) * sx,
                             ty + (rect.y1 - old_media.y0) * sy)

        annotations = [(item.xref, fitz.Rect(item.rect)) for item in (page.annots() or [])]
        widgets = [(item.xref, fitz.Rect(item.rect)) for item in (page.widgets() or [])]
        links = [(dict(item), fitz.Rect(item["from"])) for item in page.get_links()]
        old_boxes = {"crop": fitz.Rect(page.cropbox), "bleed": fitz.Rect(page.bleedbox),
                     "trim": fitz.Rect(page.trimbox), "art": fitz.Rect(page.artbox)}
        contents = list(page.get_contents())
        if contents:
            prefix = document.get_new_xref(); document.update_object(prefix, "<<>>")
            document.update_stream(prefix, f"q {sx:.9f} 0 0 {sy:.9f} {tx:.9f} {ty:.9f} cm\n".encode("ascii"))
            suffix = document.get_new_xref(); document.update_object(suffix, "<<>>")
            document.update_stream(suffix, b"Q\n")
            references = " ".join(f"{xref} 0 R" for xref in [prefix, *contents, suffix])
            document.xref_set_key(page.xref, "Contents", f"[{references}]")
        page.set_mediabox(fitz.Rect(0, 0, width, height))
        page = document.reload_page(page)
        annotations_by_xref = {item.xref: item for item in (page.annots() or [])}
        for xref, rectangle in annotations:
            item = annotations_by_xref.get(xref)
            if item:
                item.set_rect(transformed(rectangle)); item.update()
        widgets_by_xref = {item.xref: item for item in (page.widgets() or [])}
        for xref, rectangle in widgets:
            item = widgets_by_xref.get(xref)
            if item:
                item.rect = transformed(rectangle); item.update()
        links_by_xref = {item.get("xref"): item for item in page.get_links()}
        for original, rectangle in links:
            current = links_by_xref.get(original.get("xref"))
            if current:
                current["from"] = transformed(rectangle)
                page.update_link(current)
        full_old = fitz.Rect(0, 0, old_width, old_height)
        for name, box in old_boxes.items():
            target = fitz.Rect(0, 0, width, height) if box == full_old else transformed(box)
            target &= page.mediabox
            if target.is_empty:
                continue
            {"crop": page.set_cropbox, "bleed": page.set_bleedbox,
             "trim": page.set_trimbox, "art": page.set_artbox}[name](target)

    @staticmethod
    def _page_index(document: fitz.Document, value) -> int:
        index = int(value or 0) - 1
        if index < 0 or index >= document.page_count: raise ValueError("An edit refers to a page that does not exist")
        return index


def color(value: str) -> tuple[float, float, float]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value): raise ValueError("Invalid PDF color")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))


def _digest_hex(value) -> str:
    if isinstance(value, bytes):
        return value.hex().lower()
    return str(value or "").lower()


def _line_end(value: str) -> int:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return {
        "none": fitz.PDF_ANNOT_LE_NONE, "square": fitz.PDF_ANNOT_LE_SQUARE,
        "circle": fitz.PDF_ANNOT_LE_CIRCLE, "diamond": fitz.PDF_ANNOT_LE_DIAMOND,
        "open_arrow": fitz.PDF_ANNOT_LE_OPEN_ARROW, "closed_arrow": fitz.PDF_ANNOT_LE_CLOSED_ARROW,
        "butt": fitz.PDF_ANNOT_LE_BUTT, "reverse_open_arrow": fitz.PDF_ANNOT_LE_R_OPEN_ARROW,
        "reverse_closed_arrow": fitz.PDF_ANNOT_LE_R_CLOSED_ARROW, "slash": fitz.PDF_ANNOT_LE_SLASH,
    }.get(normalized, fitz.PDF_ANNOT_LE_NONE)


def _stamp_number(value: str | None) -> int:
    normalized = str(value or "draft").strip().lower().replace(" ", "_")
    return {
        "draft": 0, "approved": 1, "experimental": 2, "not_approved": 3,
        "as_is": 4, "expired": 5, "not_for_public_release": 6,
        "confidential": 7, "final": 8, "sold": 9, "departmental": 10,
        "for_comment": 11, "top_secret": 12, "for_public_release": 13,
    }.get(normalized, 0)


def normalize_rotation(value) -> int:
    rotation = int(value) % 360
    if rotation not in {0, 90, 180, 270}: raise ValueError("PDF rotation must be 0, 90, 180, or 270 degrees")
    return rotation


def safe_attachment_name(value: str) -> str:
    name = Path(value).name.strip()
    if not name or name in {".", ".."} or any(ord(character) < 32 for character in name):
        raise ValueError("Embedded attachment name is invalid")
    return name[:255]


def resolve_font(requested: str) -> tuple[str, str | None]:
    builtins = {"helvetica": "helv", "arial": "helv", "times": "tiro", "times new roman": "tiro",
                "courier": "cour", "symbol": "symb", "zapfdingbats": "zapfdingbats"}
    normalized = requested.strip().lower()
    if normalized in builtins: return builtins[normalized], None
    if not re.fullmatch(r"[\w .,+-]{1,120}", requested): raise ValueError("Font family name contains unsupported characters")
    if not shutil.which("fc-match"): raise ValueError(f"Font '{requested}' is not installed")
    result = subprocess.run(["fc-match", "--format", "%{file}", requested], capture_output=True, text=True, timeout=10, check=True)
    fontfile = result.stdout.strip()
    if not fontfile or not Path(fontfile).is_file(): raise ValueError(f"Font '{requested}' is not installed")
    return "cvfont", fontfile


def validate_edited_pdf(source: Path, output: Path, operations: list[dict]) -> dict:
    """Validate structure, expected edits, rendering, and untouched-page fidelity."""
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("Edited PDF validation failed: the output is empty")
    structural = any(operation["kind"] in {"page.reorder", "page.delete", "page.insert_blank",
                                                   "page.insert_from_pdf", "page.replace_from_pdf"}
                     for operation in operations)
    global_change = any(operation["kind"] in {"watermark.text", "header_footer", "metadata.set"}
                        for operation in operations)
    changed_pages: set[int] = set()
    expected_pages = None
    errors: list[str] = []
    warnings: list[str] = []
    redaction_checks: list[dict] = []
    unchanged_hashes: list[dict] = []
    with fitz.open(source) as original, fitz.open(output) as edited:
        expected_pages = original.page_count
        for operation in operations:
            kind = operation["kind"]
            if operation.get("page"):
                changed_pages.add(int(operation["page"]))
            changed_pages.update(int(page) for page in operation.get("pages", []))
            if kind == "page.delete": expected_pages -= len(set(operation["pages"]))
            if kind in {"page.insert_blank", "page.insert_from_pdf"}: expected_pages += 1
            if kind in {"page.reorder", "watermark.text", "header_footer", "metadata.set"}:
                changed_pages.update(range(1, edited.page_count + 1))
        if edited.page_count != expected_pages:
            errors.append(f"Expected {expected_pages} pages but the output has {edited.page_count}")
        if edited.needs_pass:
            errors.append("The exported PDF unexpectedly requires a password")
        for page_number in sorted(page for page in changed_pages if 1 <= page <= edited.page_count):
            page = edited[page_number - 1]
            try:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                if not pixmap.samples:
                    errors.append(f"Page {page_number} rendered no pixels")
                page.get_text("text")
                page.get_fonts(full=True)
            except Exception as exc:
                errors.append(f"Page {page_number} did not render or parse: {str(exc)[:160]}")
        for operation in operations:
            page_number = operation.get("page")
            if operation["kind"] == "redact.search":
                selected = operation.get("pages") or list(range(1, edited.page_count + 1))
                output_text = "\n".join(edited[number - 1].get_text("text") for number in selected
                                        if 1 <= number <= edited.page_count)
                remaining = [term for term in operation.get("search_terms", [])
                             if term and term.casefold() in output_text.casefold()]
                if operation.get("custom_regex") and re.search(operation["custom_regex"], output_text,
                                                                0 if operation.get("case_sensitive") else re.IGNORECASE):
                    remaining.append("custom_regex")
                if remaining:
                    errors.append("Search redaction left matched content extractable: " + ", ".join(remaining[:5]))
                redaction_checks.append({"pages": selected, "terms": len(operation.get("search_terms", [])),
                                         "pattern_type": operation.get("pattern_type"),
                                         "remaining_matches": remaining,
                                         "metadata_removed": bool(operation.get("remove_metadata")),
                                         "comments_removed": bool(operation.get("remove_comments")),
                                         "attachments_removed": bool(operation.get("remove_attachments")),
                                         "hidden_text_scrubbed": bool(operation.get("remove_hidden_text", True)),
                                         "form_values_removed": bool(operation.get("remove_form_values"))})
            if not page_number or page_number > edited.page_count:
                continue
            page_text = edited[page_number - 1].get_text("text")
            if operation["kind"] == "content.replace_text":
                if operation["text"] in page_text:
                    errors.append(f"Replaced source text remains extractable on page {page_number}")
                replacement = operation.get("replacement", "")
                if replacement and replacement not in page_text:
                    errors.append(f"Replacement text is not extractable on page {page_number}")
            if operation["kind"] == "content.edit_text_object":
                original_text = operation["text"]
                start, end = int(operation["range_start"]), int(operation["range_end"])
                rebuilt = original_text[:start] + operation.get("replacement", "") + original_text[end:]
                if original_text != rebuilt and original_text in page_text:
                    errors.append(f"The original native text object remains extractable on page {page_number}")
                if rebuilt and rebuilt not in page_text:
                    errors.append(f"The edited native text object is not extractable on page {page_number}")
            if operation["kind"] == "content.add_text" and operation.get("text") not in page_text:
                errors.append(f"Added text is not extractable on page {page_number}")
            if operation["kind"] in {"page.insert_from_pdf", "page.replace_from_pdf"}:
                sample = operation.get("text")
                if sample and sample not in page_text:
                    errors.append(f"Imported page text is not extractable at page {page_number}")
            if operation["kind"] == "page.resize":
                page_rect = edited[page_number - 1].mediabox
                if abs(page_rect.width - float(operation["page_width"])) > 0.1 or abs(page_rect.height - float(operation["page_height"])) > 0.1:
                    errors.append(f"Page {page_number} does not have the requested resized dimensions")
            if operation["kind"] == "page.set_boxes":
                edited_page = edited[page_number - 1]
                actual_boxes = {"media": edited_page.mediabox, "crop": edited_page.cropbox,
                                "bleed": edited_page.bleedbox, "trim": edited_page.trimbox,
                                "art": edited_page.artbox}
                for name, expected in operation.get("page_boxes", {}).items():
                    if any(abs(a - b) > 0.1 for a, b in zip(actual_boxes[name], expected)):
                        errors.append(f"Page {page_number} {name} box does not match the requested coordinates")
            if operation["kind"] in {"content.transform_image", "content.replace_image_object"}:
                destination = fitz.Rect(operation["rect"])
                images = edited[page_number - 1].get_image_info(xrefs=True)
                if not any(fitz.Rect(item["bbox"]).intersects(destination) for item in images):
                    errors.append(f"The edited image is not rendered at its destination on page {page_number}")
            if operation["kind"] == "content.delete_image_object":
                source_bounds = fitz.Rect(operation["source_rect"])
                images = edited[page_number - 1].get_image_info(xrefs=True)
                if any(fitz.Rect(item["bbox"]).intersects(source_bounds) for item in images):
                    errors.append(f"The deleted image remains rendered on page {page_number}")
            if operation["kind"] == "content.transform_vector":
                destination = fitz.Rect(operation["rect"])
                drawings = edited[page_number - 1].get_drawings()
                if not any(fitz.Rect(item["rect"]).intersects(destination) for item in drawings):
                    errors.append(f"The edited vector path is not rendered at its destination on page {page_number}")
            if operation["kind"] == "content.delete_vector_object":
                source_bounds = fitz.Rect(operation["source_rect"])
                drawings = edited[page_number - 1].get_drawings()
                if any(fitz.Rect(item["rect"]).intersects(source_bounds) for item in drawings):
                    errors.append(f"The deleted vector path remains rendered on page {page_number}")
            if operation["kind"] == "redact" and operation.get("text"):
                warnings.append("Redaction appearance text was added; region content removal was render-checked")
        annotation_intent: dict[str, dict] = {}
        for operation in operations:
            name = operation.get("annotation_name")
            if operation["kind"].startswith("annotate.") and name:
                annotation_intent[name] = {
                    "present": operation["kind"] != "annotate.delete",
                    "kind": operation["kind"],
                }
        edited_annotations = {}
        for edited_page in edited:
            for annotation in edited_page.annots() or []:
                name = (annotation.info or {}).get("id")
                if name:
                    edited_annotations[name] = {"xref": annotation.xref, "type": annotation.type[1]}
        for name, expectation in annotation_intent.items():
            annotation = edited_annotations.get(name)
            if expectation["present"] and annotation is None:
                errors.append(f"Annotation {name} is missing from the exported PDF")
                continue
            if not expectation["present"] and annotation is not None:
                errors.append(f"Deleted annotation {name} remains in the exported PDF")
                continue
            if annotation is None:
                continue
            if expectation["kind"] == "annotate.reply" and edited.xref_get_key(annotation["xref"], "IRT")[0] != "xref":
                errors.append(f"Annotation reply {name} is not linked to its parent thread")
            if expectation["kind"] == "annotate.attachment" and annotation["type"] != "FileAttachment":
                errors.append(f"Annotation {name} did not retain its embedded attachment")
            if expectation["kind"] == "annotate.measurement" and edited.xref_get_key(annotation["xref"], "Measure")[0] != "dict":
                errors.append(f"Measurement annotation {name} is missing its PDF measurement dictionary")
        if not structural and original.page_count == edited.page_count:
            for index in range(original.page_count):
                page_number = index + 1
                if global_change or page_number in changed_pages:
                    continue
                original_png = original[index].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png")
                edited_png = edited[index].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).tobytes("png")
                original_hash = hashlib.sha256(original_png).hexdigest()
                edited_hash = hashlib.sha256(edited_png).hexdigest()
                identical = original_hash == edited_hash
                unchanged_hashes.append({"page": page_number, "identical": identical,
                                         "source_sha256": original_hash, "output_sha256": edited_hash})
                if not identical:
                    errors.append(f"Unchanged page {page_number} rendered differently")
        signature_count = sum(1 for page in original for widget in (page.widgets() or [])
                              if "Sig" in str(widget.field_type_string))
    try:
        independent_reader = PdfReader(str(output), strict=True)
        independent_page_count = len(independent_reader.pages)
        if independent_page_count != expected_pages:
            errors.append("Independent PDF parser reported an unexpected page count")
    except Exception as exc:
        independent_page_count = None
        errors.append(f"Independent PDF parser rejected the output: {str(exc)[:160]}")
    report = {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "expected_page_count": expected_pages,
        "output_page_count": independent_page_count,
        "changed_pages": sorted(changed_pages),
        "unchanged_page_fidelity": unchanged_hashes,
        "signature_impact": {
            "source_signature_fields": signature_count,
            "prior_signatures_invalidated": bool(signature_count and operations),
        },
        "redaction_report": redaction_checks,
        "validators": ["PyMuPDF reopen/render/text/font", "pypdf strict parser"],
    }
    if errors:
        raise RuntimeError("Edited PDF validation failed: " + "; ".join(errors[:5]))
    return report
