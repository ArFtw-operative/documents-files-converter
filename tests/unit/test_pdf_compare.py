import fitz

from convertvault.pdf_compare import compare_pdfs


def _document(path, revised=False):
    document = fitz.open()
    first = document.new_page(width=400, height=500)
    first.insert_text((40, 60), "Approved contract" if revised else "Draft contract", fontsize=13 if revised else 11)
    first.insert_text((40, 82), "Shared styled phrase", fontsize=14 if revised else 10)
    first.draw_rect(fitz.Rect(40, 100, 150, 150), fill=(0.8, 0.9, 1) if revised else (0.8, 1, 0.8))
    if revised:
        first.add_text_annot((180, 100), "New review note")
        widget = fitz.Widget(); widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        widget.field_name = "approval"; widget.field_value = "Yes"; widget.rect = fitz.Rect(40, 180, 180, 210)
        first.add_widget(widget)
    second = document.new_page(width=400, height=500); second.insert_text((40, 60), "Unchanged appendix")
    if revised:
        document.move_page(1, 0)
        document.set_metadata({"title": "Revised document"})
        inserted = document.new_page(); inserted.insert_text((40, 60), "Inserted schedule")
    else:
        document.set_metadata({"title": "Original document"})
    document.save(path); document.close()


def test_text_object_page_and_visual_comparison_report(tmp_path):
    before, after = tmp_path / "before.pdf", tmp_path / "after.pdf"
    _document(before); _document(after, revised=True)
    report = compare_pdfs(before, after, {"ignore_whitespace": True})
    kinds = {item["type"] for item in report["differences"]}
    assert report["text_aware"] is True and report["visual_comparison"] is True
    assert report["before_pages"] == 2 and report["after_pages"] == 3
    assert "page_moved" in kinds and "page_inserted" in kinds
    assert "text_replaced" in kinds
    assert "style_changed" in kinds
    assert "annotation_changed" in kinds
    assert "form_field_changed" in kinds
    assert "metadata_changed" in kinds
    assert "visual_changed" in kinds
    assert report["summary"]["total"] == len(report["differences"])
    assert all(len(item["id"]) == 24 and item["reviewed"] is False for item in report["differences"])
