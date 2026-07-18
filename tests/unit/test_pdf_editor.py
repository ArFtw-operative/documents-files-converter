import fitz

from convertvault.engines.base import ConversionContext
from convertvault.engines.pdf_editor import PdfEditorEngine, validate_edited_pdf
from convertvault.pdf_scene import build_page_scene


def make_pdf(path):
    document = fitz.open()
    for number in range(2):
        page = document.new_page(width=400, height=500)
        page.insert_text((40, 60), f"Private draft {number + 1}")
    document.save(path)


def edit(source, destination, operations, files=None):
    context = ConversionContext(
        source,
        destination,
        "pdf",
        "pdf",
        {"operations": operations, "_additional_file_map": files or {}},
    )
    return PdfEditorEngine().convert(context)


def test_editor_applies_content_annotations_links_forms_and_metadata(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "edited.pdf"
    make_pdf(source)
    edit(source, output, [
        {"kind": "content.replace_text", "page": 1, "text": "Private draft 1", "replacement": "Approved copy", "font_size": 11},
        {"kind": "content.add_text", "page": 1, "rect": [40, 90, 250, 120], "text": "Added by PDF Studio", "font": "Helvetica", "font_size": 12},
        {"kind": "content.add_shape", "page": 1, "rect": [35, 130, 180, 175], "text": "rectangle", "color": "#176b4d", "fill": "#dff4e9"},
        {"kind": "annotate.comment", "page": 1, "rect": [40, 190, 80, 220], "text": "Review this section"},
        {"kind": "link.add", "page": 1, "rect": [40, 230, 220, 250], "uri": "https://example.com"},
        {"kind": "form.text", "page": 1, "rect": [40, 270, 220, 300], "field_name": "customer_name", "text": "Name"},
        {"kind": "metadata.set", "metadata": {"title": "Edited locally", "author": "ConvertVault"}},
    ])
    with fitz.open(output) as document:
        page = document[0]
        text = page.get_text()
        assert "Private draft 1" not in text
        assert "Approved copy" in text and "Added by PDF Studio" in text
        assert document.metadata["title"] == "Edited locally"
        assert any(link.get("uri") == "https://example.com" for link in page.get_links())
        assert any(widget.field_name == "customer_name" for widget in (page.widgets() or []))
        assert sum(1 for _ in (page.annots() or [])) >= 1


def test_editor_organizes_pages_and_permanently_redacts(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "organized.pdf"
    make_pdf(source)
    edit(source, output, [
        {"kind": "page.reorder", "order": [2, 1]},
        {"kind": "page.rotate", "page": 1, "rotation": 90},
        {"kind": "redact", "page": 2, "rect": [35, 40, 180, 75], "fill": "#000000"},
        {"kind": "page.insert_blank", "page": 3, "page_width": 400, "page_height": 500},
    ])
    with fitz.open(output) as document:
        assert document.page_count == 3
        assert document[0].rotation == 90
        assert "Private draft 2" in document[0].get_text()
        assert "Private draft 1" not in document[1].get_text()


def test_editor_adds_image_asset_and_rejects_unsafe_links(tmp_path):
    source, output, image = tmp_path / "source.pdf", tmp_path / "image.pdf", tmp_path / "mark.png"
    make_pdf(source)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
    pixmap.clear_with(0x176B4D)
    pixmap.save(image)
    edit(source, output, [{"kind": "content.add_image", "page": 1, "rect": [250, 40, 330, 120], "image_file_id": "mark"}], {"mark": str(image)})
    with fitz.open(output) as document:
        assert len(document[0].get_images(full=True)) == 1

    try:
        edit(source, tmp_path / "unsafe.pdf", [{"kind": "link.add", "page": 1, "rect": [10, 10, 40, 40], "uri": "javascript:alert(1)"}])
    except ValueError as error:
        assert "HTTP(S)" in str(error)
    else:
        raise AssertionError("Unsafe links must be rejected")


def test_existing_link_can_update_and_delete(tmp_path):
    source, updated, deleted = tmp_path / "link.pdf", tmp_path / "link-updated.pdf", tmp_path / "link-deleted.pdf"
    with fitz.open() as document:
        page = document.new_page(width=400, height=500)
        page.insert_text((40, 60), "Visit link")
        page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(40, 40, 130, 70),
                          "uri": "https://example.com/old"})
        document.save(source)
    link = next(item for item in build_page_scene(
        source, "99999999-9999-4999-8999-999999999999", 1
    )["objects"] if item["type"] == "link")
    update = {"kind": "link.update", "page": 1, "source_xref": link["source"]["xref"],
              "uri": "https://example.com/new"}
    edit(source, updated, [update])
    with fitz.open(updated) as document:
        assert document[0].get_links()[0]["uri"] == "https://example.com/new"
    remove = {"kind": "link.delete", "page": 1, "source_xref": link["source"]["xref"]}
    edit(source, deleted, [remove])
    with fitz.open(deleted) as document:
        assert document[0].get_links() == []


def test_edit_validation_renders_changes_and_proves_untouched_page_fidelity(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "validated.pdf"
    make_pdf(source)
    operations = [{"kind": "content.add_text", "page": 1, "rect": [40, 100, 260, 130],
                   "text": "Validated native addition", "font": "Helvetica", "font_size": 11}]
    edit(source, output, operations)
    report = validate_edited_pdf(source, output, operations)
    assert report["valid"] is True
    assert report["changed_pages"] == [1]
    assert len(report["unchanged_page_fidelity"]) == 1
    assert report["unchanged_page_fidelity"][0]["page"] == 2
    assert report["unchanged_page_fidelity"][0]["identical"] is True
    assert len(report["validators"]) == 2


def test_edit_validation_rejects_an_output_that_did_not_apply_expected_text(tmp_path):
    source, unchanged = tmp_path / "source.pdf", tmp_path / "unchanged.pdf"
    make_pdf(source)
    unchanged.write_bytes(source.read_bytes())
    operations = [{"kind": "content.add_text", "page": 1, "rect": [40, 100, 260, 130],
                   "text": "This must exist", "font": "Helvetica", "font_size": 11}]
    try:
        validate_edited_pdf(source, unchanged, operations)
    except RuntimeError as error:
        assert "Added text is not extractable" in str(error)
    else:
        raise AssertionError("Validation must reject a missing expected edit")


def test_native_text_object_range_edit_preserves_style_and_creates_searchable_content(tmp_path):
    source, output = tmp_path / "source.pdf", tmp_path / "native-edit.pdf"
    make_pdf(source)
    scene = build_page_scene(source, "33333333-3333-4333-8333-333333333333", 1)
    text_object = next(item for item in scene["objects"] if item["type"] == "text_run")
    original = text_object["text"]
    start = original.index("draft")
    operation = {
        "kind": "content.edit_text_object",
        "page": 1,
        "object_id": text_object["id"],
        "rect": text_object["bounds"],
        "origin": text_object["transform"][4:6],
        "text": original,
        "replacement": "final",
        "range_start": start,
        "range_end": start + len("draft"),
        "font": text_object["style"]["font"],
        "font_size": text_object["style"]["font_size"],
        "font_resource": text_object["style"]["font_resource"],
        "font_xref": text_object["style"]["font_xref"],
        "color": text_object["style"]["color"],
        "reflow_policy": "preserve_line_positions",
        "font_policy": "preserve_or_prompt",
    }
    edit(source, output, [operation])
    report = validate_edited_pdf(source, output, [operation])
    with fitz.open(output) as document:
        page = document[0]
        assert "Private final 1" in page.get_text()
        assert "Private draft 1" not in page.get_text()
        assert sum(1 for _ in (page.annots() or [])) == 0
        span = page.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
        assert round(span["size"], 1) == round(text_object["style"]["font_size"], 1)
        assert f"#{int(span['color']) & 0xFFFFFF:06x}" == text_object["style"]["color"]
    assert report["valid"] is True


def test_multiline_paragraph_is_a_real_scene_object_and_reflows_when_edited(tmp_path):
    source, output = tmp_path / "paragraph.pdf", tmp_path / "paragraph-edited.pdf"
    with fitz.open() as document:
        page = document.new_page(width=420, height=500)
        page.insert_textbox(
            fitz.Rect(40, 50, 360, 150),
            "First line of the original paragraph.\nSecond line stays in the same block.",
            fontname="helv",
            fontsize=12,
        )
        document.save(source)

    scene = build_page_scene(source, "88888888-8888-4888-8888-888888888888", 1)
    paragraph = next(item for item in scene["objects"] if item["type"] == "text_block")
    assert paragraph["line_count"] == 2
    assert paragraph["style"]["font_resource"]
    replacement = "This paragraph was edited as a complete multiline block.\nIts second line is searchable too."
    operation = {
        "kind": "content.edit_text_block",
        "page": 1,
        "object_id": paragraph["id"],
        "rect": paragraph["bounds"],
        "origin": paragraph["bounds"][:2],
        "text": paragraph["text"],
        "replacement": replacement,
        "range_start": 0,
        "range_end": len(paragraph["text"]),
        "font": "Helvetica",
        "font_size": paragraph["style"]["font_size"],
        "font_resource": paragraph["style"]["font_resource"],
        "font_xref": paragraph["style"]["font_xref"],
        "color": paragraph["style"]["color"],
        "reflow_policy": "reduce_font",
        "font_policy": "preserve_or_prompt",
    }
    edit(source, output, [operation])
    report = validate_edited_pdf(source, output, [operation])
    with fitz.open(output) as document:
        text = " ".join(document[0].get_text("text").split())
        assert "original paragraph" not in text
        assert "This paragraph was edited as a complete multiline block." in text
        assert "Its second line is searchable too." in text
        assert sum(1 for _ in (document[0].annots() or [])) == 0
    assert report["valid"] is True


def test_text_validation_is_region_aware_and_allows_later_overlapping_edits(tmp_path):
    source, output = tmp_path / "region-source.pdf", tmp_path / "region-edited.pdf"
    with fitz.open() as document:
        page = document.new_page(width=420, height=500)
        page.insert_text((40, 60), "Repeated title")
        page.insert_text((40, 300), "Repeated title remains elsewhere")
        document.save(source)
    paragraph = next(item for item in build_page_scene(
        source, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 1
    )["objects"] if item["type"] == "text_block" and item["text"] == "Repeated title")
    add_rect = [*paragraph["bounds"]]
    add_rect[3] += 30
    add = {"kind": "content.add_text", "page": 1, "rect": add_rect,
           "text": "Temporary", "font": "Helvetica", "font_size": 6}
    replace = {
        "kind": "content.edit_text_block", "page": 1, "object_id": paragraph["id"],
        "rect": paragraph["bounds"], "origin": paragraph["bounds"][:2],
        "text": paragraph["text"], "replacement": "English Translated",
        "range_start": 0, "range_end": len(paragraph["text"]),
        "font": paragraph["style"]["font"], "font_size": paragraph["style"]["font_size"],
        "font_resource": paragraph["style"]["font_resource"],
        "font_xref": paragraph["style"]["font_xref"], "color": paragraph["style"]["color"],
        "reflow_policy": "reduce_font", "font_policy": "preserve_or_prompt",
    }
    edit(source, output, [add, replace])
    assert validate_edited_pdf(source, output, [add, replace])["valid"] is True
    with fitz.open(output) as document:
        text = document[0].get_text("text")
        assert "English Translated" in text
        assert "Temporary" not in text
        assert "Repeated title remains elsewhere" in text


def make_object_pdf(path):
    document = fitz.open()
    page = document.new_page(width=500, height=500)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), False)
    pixmap.clear_with(0xCC4422)
    page.insert_image(fitz.Rect(40, 40, 140, 115), stream=pixmap.tobytes("png"))
    page.draw_rect(fitz.Rect(40, 180, 140, 240), color=(0.1, 0.5, 0.2),
                   fill=(0.8, 0.95, 0.85), width=3)
    document.save(path)


def test_existing_image_object_can_move_resize_rotate_crop_replace_and_delete(tmp_path):
    source = tmp_path / "objects.pdf"
    moved = tmp_path / "image-moved.pdf"
    deleted = tmp_path / "image-deleted.pdf"
    replacement = tmp_path / "replacement.png"
    make_object_pdf(source)
    replacement_pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 24, 24), False)
    replacement_pixmap.clear_with(0x176B4D)
    replacement_pixmap.save(replacement)
    image_object = next(item for item in build_page_scene(
        source, "44444444-4444-4444-8444-444444444444", 1
    )["objects"] if item["type"] == "image")
    operation = {
        "kind": "content.transform_image", "page": 1, "object_id": image_object["id"],
        "source_rect": image_object["bounds"], "source_xref": image_object["source"]["xref"],
        "rect": [260, 60, 430, 190], "rotation": 37, "crop": [0.1, 0.1, 0.9, 0.9],
    }
    edit(source, moved, [operation])
    assert validate_edited_pdf(source, moved, [operation])["valid"] is True
    with fitz.open(moved) as document:
        boxes = [fitz.Rect(item["bbox"]) for item in document[0].get_image_info(xrefs=True)]
        assert any(box.intersects(fitz.Rect(operation["rect"])) for box in boxes)
        assert not any(box.intersects(fitz.Rect(image_object["bounds"])) for box in boxes)

    delete_operation = {**operation, "kind": "content.delete_image_object",
                        "rect": image_object["bounds"], "rotation": 0, "crop": None}
    edit(source, deleted, [delete_operation])
    assert validate_edited_pdf(source, deleted, [delete_operation])["valid"] is True

    replaced = tmp_path / "image-replaced.pdf"
    replace_operation = {**operation, "kind": "content.replace_image_object",
                         "image_file_id": "replacement", "rotation": 0, "crop": None}
    edit(source, replaced, [replace_operation], {"replacement": str(replacement)})
    assert validate_edited_pdf(source, replaced, [replace_operation])["valid"] is True


def test_existing_vector_object_can_transform_restyle_rotate_and_delete(tmp_path):
    source = tmp_path / "vectors.pdf"
    transformed = tmp_path / "vector-transformed.pdf"
    deleted = tmp_path / "vector-deleted.pdf"
    make_object_pdf(source)
    vector = next(item for item in build_page_scene(
        source, "55555555-5555-4555-8555-555555555555", 1
    )["objects"] if item["type"] == "vector_path")
    operation = {
        "kind": "content.transform_vector", "page": 1, "object_id": vector["id"],
        "source_rect": vector["bounds"], "rect": [250, 260, 430, 360], "rotation": 22,
        "color": "#123456", "fill": "#dceeff", "width": 5, "opacity": 0.7,
        "vector_properties": vector["properties"],
    }
    edit(source, transformed, [operation])
    assert validate_edited_pdf(source, transformed, [operation])["valid"] is True
    with fitz.open(transformed) as document:
        drawings = document[0].get_drawings()
        assert any(fitz.Rect(item["rect"]).intersects(fitz.Rect(operation["rect"])) for item in drawings)
        assert not any(fitz.Rect(item["rect"]).intersects(fitz.Rect(vector["bounds"])) for item in drawings)

    delete_operation = {**operation, "kind": "content.delete_vector_object",
                        "rect": vector["bounds"], "rotation": 0}
    edit(source, deleted, [delete_operation])
    assert validate_edited_pdf(source, deleted, [delete_operation])["valid"] is True


def make_import_pdf(path):
    document = fitz.open()
    page = document.new_page(width=320, height=420)
    page.insert_text((35, 55), "Imported source page", fontsize=14)
    page.add_text_annot((35, 90), "Imported annotation")
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(35, 125, 180, 145),
                      "uri": "https://example.com/imported"})
    widget = fitz.Widget(); widget.field_name = "imported_name"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT; widget.rect = fitz.Rect(35, 180, 210, 210)
    widget.field_value = "Imported field"; page.add_widget(widget)
    document.save(path)


def test_page_import_and_replacement_preserve_interactive_page_objects(tmp_path):
    source, imported, output = tmp_path / "source.pdf", tmp_path / "imported.pdf", tmp_path / "pages.pdf"
    make_pdf(source); make_import_pdf(imported)
    operations = [
        {"kind": "page.replace_from_pdf", "page": 1, "source_file_id": "external",
         "source_page": 1, "text": "Imported source page"},
        {"kind": "page.insert_from_pdf", "page": 3, "source_file_id": "external",
         "source_page": 1, "text": "Imported source page"},
    ]
    edit(source, output, operations, {"external": str(imported)})
    report = validate_edited_pdf(source, output, operations)
    with fitz.open(output) as document:
        assert document.page_count == 3
        for index in (0, 2):
            page = document[index]
            assert "Imported source page" in page.get_text()
            assert sum(1 for _ in (page.annots() or [])) == 1
            assert any(link.get("uri") == "https://example.com/imported" for link in page.get_links())
            assert any(widget.field_name.startswith("imported_name") for widget in (page.widgets() or []))
    assert report["valid"] is True


def test_page_resize_scales_content_annotations_forms_links_and_page_boxes(tmp_path):
    source, output = tmp_path / "geometry-source.pdf", tmp_path / "geometry.pdf"
    document = fitz.open()
    page = document.new_page(width=400, height=500)
    page.insert_text((40, 60), "Scaled page content", fontsize=12)
    annotation = page.add_rect_annot(fitz.Rect(40, 100, 140, 150)); annotation.update()
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(40, 180, 180, 205),
                      "uri": "https://example.com/scaled"})
    widget = fitz.Widget(); widget.field_name = "scaled_field"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT; widget.rect = fitz.Rect(40, 230, 200, 260)
    widget.field_value = "Scaled"; page.add_widget(widget)
    second = document.new_page(width=400, height=500); second.insert_text((40, 60), "Untouched page")
    document.save(source); document.close()
    operations = [
        {"kind": "page.resize", "page": 1, "page_width": 800, "page_height": 700,
         "resize_mode": "fit"},
        {"kind": "page.set_boxes", "page": 1,
         "page_boxes": {"crop": [10, 10, 790, 690], "trim": [20, 20, 780, 680],
                        "bleed": [15, 15, 785, 685], "art": [30, 30, 770, 670]}},
    ]
    edit(source, output, operations)
    report = validate_edited_pdf(source, output, operations)
    with fitz.open(output) as document:
        page = document[0]
        assert tuple(round(value, 1) for value in (page.rect.width, page.rect.height)) == (780.0, 680.0)
        assert "Scaled page content" in page.get_text()
        assert sum(1 for _ in (page.annots() or [])) == 1
        assert any(link.get("uri") == "https://example.com/scaled" for link in page.get_links())
        assert any(widget.field_name == "scaled_field" for widget in (page.widgets() or []))
        assert list(page.trimbox) == [20.0, 20.0, 780.0, 680.0]
        assert "Untouched page" in document[1].get_text()
    assert report["valid"] is True
    assert report["unchanged_page_fidelity"][0]["identical"] is True


def test_required_annotation_types_properties_threads_status_and_attachment_are_real_pdf_objects(tmp_path):
    source, output = tmp_path / "annotation-source.pdf", tmp_path / "annotations.pdf"
    attachment = tmp_path / "evidence.txt"; attachment.write_text("local evidence", encoding="utf-8")
    document = fitz.open(); page = document.new_page(width=700, height=900)
    page.insert_text((40, 50), "Markup target one\nMarkup target two", fontsize=12)
    document.save(source); document.close()
    common = {"page": 1, "author": "Reviewer", "subject": "Review", "color": "#176b4d",
              "fill": "#dff4e9", "opacity": 0.75, "width": 2, "printable": True,
              "visible": True, "border_style": "dashed"}
    operations = [
        {**common, "kind": "annotate.highlight", "rect": [40, 38, 190, 55], "quads": [[40, 38, 190, 38, 40, 55, 190, 55]], "annotation_name": "highlight-1"},
        {**common, "kind": "annotate.underline", "rect": [40, 55, 190, 72], "annotation_name": "underline-1"},
        {**common, "kind": "annotate.squiggly", "rect": [210, 38, 360, 55], "annotation_name": "squiggly-1"},
        {**common, "kind": "annotate.strikeout", "rect": [210, 55, 360, 72], "annotation_name": "strikeout-1"},
        {**common, "kind": "annotate.comment", "rect": [40, 100, 70, 130], "text": "Root comment", "annotation_name": "comment-root"},
        {**common, "kind": "annotate.free_text", "rect": [90, 100, 250, 145], "text": "Free text", "annotation_name": "free-text-1"},
        {**common, "kind": "annotate.callout", "rect": [270, 100, 430, 150], "points": [[250, 125], [270, 125]], "text": "Callout", "annotation_name": "callout-1"},
        {**common, "kind": "annotate.ink", "points": [[40, 190], [80, 175], [120, 200]], "annotation_name": "ink-1"},
        {**common, "kind": "annotate.line", "points": [[160, 180], [260, 205]], "annotation_name": "line-1"},
        {**common, "kind": "annotate.arrow", "points": [[290, 180], [390, 205]], "annotation_name": "arrow-1"},
        {**common, "kind": "annotate.rectangle", "rect": [40, 240, 150, 300], "annotation_name": "rectangle-1"},
        {**common, "kind": "annotate.ellipse", "rect": [180, 240, 290, 300], "annotation_name": "ellipse-1"},
        {**common, "kind": "annotate.polygon", "points": [[330, 300], [380, 240], [430, 300]], "annotation_name": "polygon-1"},
        {**common, "kind": "annotate.polyline", "points": [[470, 240], [520, 300], [580, 250]], "annotation_name": "polyline-1"},
        {**common, "kind": "annotate.stamp", "rect": [40, 340, 190, 390], "stamp_type": "approved", "annotation_name": "stamp-1"},
        {**common, "kind": "annotate.attachment", "rect": [220, 340, 250, 370], "attachment_file_id": "evidence", "text": "Evidence", "annotation_name": "attachment-1"},
        {**common, "kind": "annotate.caret", "rect": [290, 340, 320, 370], "annotation_name": "caret-1"},
        {**common, "kind": "annotate.replace_text", "rect": [350, 340, 500, 365], "text": "Replacement suggestion", "annotation_name": "replace-1"},
        {**common, "kind": "annotate.redaction_mark", "rect": [40, 430, 180, 470], "text": "REDACT", "annotation_name": "redaction-mark-1"},
        {**common, "kind": "annotate.measurement", "points": [[220, 450], [420, 450]], "rect": [220, 440, 420, 460], "measurement_scale": 0.5, "measurement_unit": "cm", "annotation_name": "measure-1"},
        {**common, "kind": "annotate.comment", "rect": [460, 430, 490, 460], "text": "Delete me", "annotation_name": "delete-me"},
        {**common, "kind": "annotate.reply", "rect": [40, 100, 70, 130], "text": "Thread reply", "annotation_name": "reply-1", "parent_annotation_name": "comment-root"},
        {**common, "kind": "annotate.update", "rect": [40, 100, 70, 130], "text": "Root comment updated", "annotation_name": "comment-root", "annotation_status": "accepted", "locked": True},
        {**common, "kind": "annotate.delete", "rect": [460, 430, 490, 460], "annotation_name": "delete-me"},
    ]
    edit(source, output, operations, {"evidence": str(attachment)})
    report = validate_edited_pdf(source, output, operations)
    with fitz.open(output) as document:
        page = document[0]
        annotations = list(page.annots() or [])
        by_name = {(item.info or {}).get("id"): item for item in annotations}
        assert len(annotations) == 21
        assert "delete-me" not in by_name
        assert by_name["comment-root"].info["content"] == "Root comment updated"
        assert by_name["comment-root"].flags & fitz.PDF_ANNOT_IS_LOCKED
        assert document.xref_get_key(by_name["comment-root"].xref, "State")[1] == "/Accepted"
        assert document.xref_get_key(by_name["reply-1"].xref, "IRT")[0] == "xref"
        assert document.xref_get_key(by_name["measure-1"].xref, "Measure")[0] == "dict"
        assert by_name["attachment-1"].type[1] == "FileAttachment"
        assert len(by_name["highlight-1"].vertices) == 4
    assert report["valid"] is True


def test_acroform_field_matrix_properties_data_and_flattening(tmp_path):
    source, output = tmp_path / "forms-source.pdf", tmp_path / "forms.pdf"
    flattened_one, flattened_all = tmp_path / "forms-one-flat.pdf", tmp_path / "forms-all-flat.pdf"
    document = fitz.open(); document.new_page(width=700, height=900); document.save(source); document.close()
    operations = [
        {"kind": "form.text", "page": 1, "rect": [40, 40, 260, 75], "field_name": "customer",
         "field_label": "Customer name", "field_value": "Ada", "default_value": "Default customer",
         "required": True, "font_size": 12, "color": "#123456", "fill": "#eef7f2",
         "max_length": 40, "validation_pattern": "^[A-Za-z ]+$", "tab_order": 1},
        {"kind": "form.multiline", "page": 1, "rect": [40, 90, 320, 155], "field_name": "notes",
         "field_value": "First line", "multiline": True, "no_scroll": True},
        {"kind": "form.checkbox", "page": 1, "rect": [350, 40, 375, 65], "field_name": "approved",
         "field_value": "Yes", "export_value": "Approved"},
        {"kind": "form.radio", "page": 1, "rect": [400, 40, 430, 70], "field_name": "priority",
         "choice_values": ["Normal", "Urgent"]},
        {"kind": "form.combo", "page": 1, "rect": [40, 180, 260, 215], "field_name": "country",
         "choice_values": ["India", "United Kingdom", "United States"], "field_value": "India"},
        {"kind": "form.listbox", "page": 1, "rect": [290, 180, 520, 250], "field_name": "departments",
         "choice_values": ["Legal", "Finance", "Operations"], "field_value": "Legal"},
        {"kind": "form.pushbutton", "page": 1, "rect": [40, 280, 180, 320], "field_name": "submit",
         "field_label": "Submit safely"},
        {"kind": "form.signature", "page": 1, "rect": [220, 280, 480, 335], "field_name": "signature"},
        {"kind": "form.date", "page": 1, "rect": [40, 370, 260, 405], "field_name": "signed_date",
         "field_value": "2026-07-19"},
        {"kind": "form.numeric", "page": 1, "rect": [290, 370, 480, 405], "field_name": "amount",
         "field_value": "1250.50", "calculation": "subtotal + tax"},
        {"kind": "form.update", "page": 1, "object_id": "customer", "field_name": "customer_name",
         "field_value": "Grace Hopper", "readonly": True, "alignment": "center"},
        {"kind": "form.import_data", "metadata": {"country": "United Kingdom", "amount": "2000"}},
    ]
    edit(source, output, operations)
    with fitz.open(output) as result:
        widgets = {widget.field_name: widget for widget in (result[0].widgets() or [])}
        assert set(widgets) == {"customer_name", "notes", "approved", "priority", "country", "departments",
                                "submit", "signature", "signed_date", "amount"}
        assert widgets["customer_name"].field_type_string == "Text" and widgets["customer_name"].field_value == "Grace Hopper"
        assert widgets["customer_name"].field_flags & fitz.PDF_FIELD_IS_READ_ONLY
        assert widgets["notes"].field_flags & 4096
        assert widgets["approved"].field_type_string == "CheckBox"
        assert widgets["priority"].field_type_string == "RadioButton"
        assert widgets["country"].field_type_string == "ComboBox" and widgets["country"].field_value == "United Kingdom"
        assert widgets["departments"].field_type_string == "ListBox"
        assert widgets["submit"].field_type_string == "Button"
        assert widgets["signature"].field_type_string == "Signature"
        assert result.xref_get_key(widgets["signed_date"].xref, "CVFormat")[1]
        assert result.xref_get_key(widgets["amount"].xref, "CVCalculation")[1]
    edit(output, flattened_one, [{"kind": "form.flatten", "page": 1, "field_name": "customer_name"}])
    with fitz.open(flattened_one) as result:
        assert "customer_name" not in {widget.field_name for widget in (result[0].widgets() or [])}
        assert len(list(result[0].widgets() or [])) == 9
    edit(flattened_one, flattened_all, [{"kind": "form.flatten"}])
    with fitz.open(flattened_all) as result:
        assert not list(result[0].widgets() or [])


def test_search_redaction_scrubs_sensitive_content_and_produces_report(tmp_path):
    source, output = tmp_path / "redaction-source.pdf", tmp_path / "redacted.pdf"
    document = fitz.open(); page = document.new_page(width=500, height=600)
    page.insert_text((40, 60), "Secret account owner: person@example.com")
    page.add_text_annot((40, 100), "Sensitive reviewer comment")
    widget = fitz.Widget(); widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_name = "secret_value"; widget.field_value = "Hidden form value"
    widget.rect = fitz.Rect(40, 140, 240, 175); page.add_widget(widget)
    document.set_metadata({"title": "Sensitive metadata"})
    document.embfile_add("evidence.txt", b"Sensitive attachment")
    document.save(source); document.close()
    operations = [{"kind": "redact.search", "pages": [1], "search_terms": ["Secret"],
                   "pattern_type": "email", "fill": "#000000", "remove_metadata": True,
                   "remove_comments": True, "remove_attachments": True, "remove_hidden_text": True,
                   "remove_form_values": True}]
    edit(source, output, operations)
    report = validate_edited_pdf(source, output, operations)
    with fitz.open(output) as result:
        assert "Secret" not in result[0].get_text() and "person@example.com" not in result[0].get_text()
        assert not list(result[0].annots() or [])
        assert not result.embfile_names()
        assert not result.metadata.get("title")
        assert all(not str(widget.field_value or "") for widget in (result[0].widgets() or []))
    assert report["valid"] is True
    assert report["redaction_report"][0]["remaining_matches"] == []
    assert report["redaction_report"][0]["hidden_text_scrubbed"] is True


def test_bookmark_and_embedded_attachment_crud_is_native_and_recoverable(tmp_path):
    source, output = tmp_path / "navigation-source.pdf", tmp_path / "navigation.pdf"
    first_asset, replacement = tmp_path / "evidence.txt", tmp_path / "replacement.txt"
    first_asset.write_text("first evidence", encoding="utf-8"); replacement.write_text("replacement evidence", encoding="utf-8")
    make_pdf(source)
    operations = [
        {"kind": "bookmark.add", "bookmark_title": "First page", "bookmark_level": 1, "target_page": 1},
        {"kind": "bookmark.add", "bookmark_title": "Second page", "bookmark_level": 1, "target_page": 2},
        {"kind": "bookmark.update", "bookmark_index": 0, "bookmark_title": "Updated first page",
         "bookmark_level": 1, "target_page": 1},
        {"kind": "bookmark.delete", "bookmark_index": 1},
        {"kind": "attachment.add", "attachment_file_id": "first", "attachment_name": "evidence.txt",
         "text": "Supporting evidence"},
        {"kind": "attachment.replace", "attachment_file_id": "replacement", "attachment_name": "evidence.txt",
         "text": "Updated evidence"},
    ]
    edit(source, output, operations, {"first": str(first_asset), "replacement": str(replacement)})
    with fitz.open(output) as result:
        toc = result.get_toc(); assert toc == [[1, "Updated first page", 1]]
        assert result.embfile_names() == ["evidence.txt"]
        assert result.embfile_get("evidence.txt") == b"replacement evidence"
        assert result.embfile_info("evidence.txt")["description"] == "Updated evidence"
    deleted = tmp_path / "navigation-deleted.pdf"
    edit(output, deleted, [{"kind": "attachment.delete", "attachment_name": "evidence.txt"}])
    with fitz.open(deleted) as result:
        assert not result.embfile_names()


def test_exposed_page_drawing_signature_watermark_header_and_form_controls_are_real(tmp_path):
    source = tmp_path / "exposed-controls-source.pdf"
    output = tmp_path / "exposed-controls.pdf"
    signature = tmp_path / "signature.png"
    make_pdf(source)
    signature_pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 24), False)
    signature_pixmap.clear_with(0x245A3A)
    signature_pixmap.save(signature)
    operations = [
        {"kind": "page.delete", "pages": [2]},
        {"kind": "page.crop", "page": 1, "rect": [20, 20, 380, 480]},
        {"kind": "content.draw", "page": 1,
         "points": [[45, 150], [90, 135], [140, 165], [190, 145]],
         "color": "#245a3a", "width": 3, "opacity": 0.9},
        {"kind": "signature.add", "page": 1, "rect": [230, 120, 350, 170],
         "image_file_id": "signature"},
        {"kind": "form.text", "page": 1, "rect": [40, 210, 220, 240],
         "field_name": "resettable", "field_value": "Changed", "default_value": "Default"},
        {"kind": "form.text", "page": 1, "rect": [40, 255, 220, 285],
         "field_name": "delete_me", "field_value": "Temporary"},
        {"kind": "form.reset"},
        {"kind": "form.delete", "page": 1, "field_name": "delete_me"},
        {"kind": "watermark.text", "text": "CONTROLLED COPY", "font_size": 20,
         "color": "#777777", "opacity": 0.25, "rotation": 0},
        {"kind": "header_footer", "text": "Verified page {page}", "font_size": 9,
         "color": "#333333"},
    ]
    edit(source, output, operations, {"signature": str(signature)})
    report = validate_edited_pdf(source, output, operations)
    with fitz.open(output) as document:
        assert document.page_count == 1
        page = document[0]
        assert tuple(round(value) for value in page.cropbox) == (20, 20, 380, 480)
        assert len(page.get_drawings()) >= 1
        assert page.get_images(full=True)
        widgets = {widget.field_name: widget for widget in (page.widgets() or [])}
        assert set(widgets) == {"resettable"}
        assert str(widgets["resettable"].field_value) == "Default"
        text = page.get_text()
        assert "CONTROLLED COPY" in text
        assert "Verified page 1" in text
    assert report["valid"] is True


def test_duplicate_page_creates_an_independent_valid_page(tmp_path):
    source, output = tmp_path / "duplicate-source.pdf", tmp_path / "duplicated.pdf"
    make_pdf(source)
    operations = [{"kind": "page.duplicate", "page": 1}]
    edit(source, output, operations)
    report = validate_edited_pdf(source, output, operations)
    with fitz.open(output) as document:
        assert document.page_count == 3
        assert "Private draft 1" in document[0].get_text()
        assert "Private draft 1" in document[1].get_text()
        assert "Private draft 2" in document[2].get_text()
        document[1].insert_text((40, 100), "Independent duplicate")
        assert "Independent duplicate" not in document[0].get_text()
    assert report["valid"] is True
