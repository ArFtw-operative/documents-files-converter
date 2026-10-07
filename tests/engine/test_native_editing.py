"""Document engine: native analysis + in-place text editing (architecture §82 vertical slice)."""

from pathlib import Path

import pymupdf as fitz
import pytest

from pdf_core.analyzer import analyze_page
from pdf_core.mutation import MutationError, apply_batch
from pdf_core.reconcile import reconcile
from pdf_core.scene import ObjectType
from pdf_core.validation import validate_revision

PAGE_UUID = "5b0a3c7e-1111-4222-8333-444455556666"


def scene(path: Path, index: int = 0):
    with fitz.open(path) as doc:
        return analyze_page(doc, index, PAGE_UUID)


def find(page_scene, text):
    return next(o for o in page_scene.objects if o.type == ObjectType.TEXT_NATIVE and o.content["text"] == text)


def norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def texts(page_scene):
    return [o.content["text"] for o in page_scene.objects if o.type == ObjectType.TEXT_NATIVE]


def edit(source: Path, tmp_path: Path, text: str, new_text: str, **payload):
    before = scene(source)
    target = find(before, text)
    output = tmp_path / "out.pdf"
    result = apply_batch(source, output, [{
        "type": "replace_text", "page_index": 0, "target_ids": [target.id],
        "payload": {"old_text": text, "new_text": new_text, **payload},
    }], lambda index: before)
    return before, target, output, result


def check_valid(source: Path, output: Path, result) -> None:
    with fitz.open(source) as doc:
        pages = doc.page_count
    report = validate_revision(source, output, pages, {0: (0, result.regions.get(0, []))})
    assert report.ok, report.as_dict()
    assert report.qpdf in ("ok", "warnings")


def test_analyzer_groups_runs_and_infers_alignment(golden):
    page_scene = scene(golden["simple_invoice.pdf"])
    assert page_scene.page_type == "NATIVE_TEXT"
    assert "VISHNU MEDICAL HALL" in texts(page_scene)
    assert find(page_scene, "4553.00").style["text_align"] == "right"
    header = find(page_scene, "VISHNU MEDICAL HALL")
    assert header.style["bold"] and header.style["fill"] == "#1a3380"
    # Every visible glyph has a quad for caret placement.
    assert len(header.content["glyphs"]) == len("VISHNU MEDICAL HALL")


def test_replace_text_is_real_text_with_original_font(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    # Every glyph needed exists in the embedded bold subset.
    before, target, output, result = edit(source, tmp_path, "VISHNU MEDICAL HALL", "VISHNU MEDICAL HALLS")
    check_valid(source, output, result)
    after = scene(output)
    edited = find(after, "VISHNU MEDICAL HALLS")
    # Same embedded glyphs; the re-embedded copy reports its PostScript name.
    assert norm(edited.style["font_name"]) == norm(target.style["font_name"])
    assert edited.style["size_pt"] == target.style["size_pt"]
    assert edited.style["fill"] == target.style["fill"]
    assert abs(edited.content["baseline_origin"][0] - target.content["baseline_origin"][0]) < 0.01
    assert abs(edited.content["baseline_origin"][1] - target.content["baseline_origin"][1]) < 0.01
    assert "font_substituted" not in result.warnings
    # Neighbours unchanged.
    assert sorted(t for t in texts(after) if t != "VISHNU MEDICAL HALLS") == \
        sorted(t for t in texts(before) if t != "VISHNU MEDICAL HALL")
    with fitz.open(output) as doc:
        assert "VISHNU MEDICAL HALLS" in doc[0].get_text()


def test_glyphs_missing_from_subset_use_the_same_installed_family(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    _, target, output, result = edit(source, tmp_path, "VISHNU MEDICAL HALL", "VISHNU MEDICAL STORES")
    check_valid(source, output, result)
    assert "font_substituted" not in result.warnings
    assert result.outcomes[0].substitutions[0]["reason"] == "same_family_installed"
    edited = find(scene(output), "VISHNU MEDICAL STORES")
    assert norm(edited.style["font_name"]) == norm(target.style["font_name"])


def test_right_aligned_amount_keeps_right_edge(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    _, target, output, result = edit(source, tmp_path, "4553.00", "45530.00")
    check_valid(source, output, result)
    edited = find(scene(output), "45530.00")
    assert abs(edited.bbox[2] - target.bbox[2]) < 0.3
    assert edited.bbox[0] < target.bbox[0]


def test_missing_glyph_uses_visually_matched_font_and_reports_it(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    _, _, output, result = edit(source, tmp_path, "4553.00", "₹4553.00")
    check_valid(source, output, result)
    assert "font_substituted" in result.warnings
    substitution = result.outcomes[0].substitutions[0]
    assert substitution["chars"] == "₹" and substitution["reason"] == "glyph_missing"
    with fitz.open(output) as doc:
        assert "₹4553.00" in doc[0].get_text()


def test_overflow_requires_confirmation_then_succeeds(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    long_text = "Amoxicillin 250mg capsules, strip of ten, sugar free, store below 25 C away from light"
    with pytest.raises(MutationError) as caught:
        edit(source, tmp_path, "Amoxicillin 250mg", long_text)
    assert caught.value.code == "needs_confirmation"
    _, _, output, result = edit(source, tmp_path, "Amoxicillin 250mg", long_text, allow_overflow=True)
    assert long_text in texts(scene(output))


def test_slightly_longer_text_is_fitted_within_limits(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    # "Qty" column limits the item cell; a modestly longer name is tracked/scaled to fit.
    _, target, output, result = edit(source, tmp_path, "Paracetamol 500mg", "Paracetamol 500mg tablets IP")
    check_valid(source, output, result)
    fit = result.outcomes[0].fit
    assert fit["hscale"] >= 0.9 and fit["size_factor"] >= 0.9


def test_stale_edit_is_rejected(golden, tmp_path):
    before = scene(golden["simple_invoice.pdf"])
    target = find(before, "4553.00")
    with pytest.raises(MutationError) as caught:
        apply_batch(golden["simple_invoice.pdf"], tmp_path / "x.pdf", [{
            "type": "replace_text", "page_index": 0, "target_ids": [target.id],
            "payload": {"old_text": "9999.00", "new_text": "1.00"}}], lambda i: before)
    assert caught.value.code == "target_modified"


@pytest.mark.parametrize("fixture", ["rotated_page.pdf", "cropped_page.pdf"])
def test_page_rotation_and_cropbox_do_not_shift_edits(golden, tmp_path, fixture):
    source = golden[fixture]
    _, target, output, result = edit(source, tmp_path, "INV-2026-0042", "INV-2026-0043")
    check_valid(source, output, result)
    edited = find(scene(output), "INV-2026-0043")
    assert abs(edited.bbox[0] - target.bbox[0]) < 0.05 and abs(edited.bbox[1] - target.bbox[1]) < 0.05
    with fitz.open(output) as doc, fitz.open(source) as original:
        assert doc[0].rotation == original[0].rotation
        assert doc[0].cropbox == original[0].cropbox


def test_rotated_text_keeps_direction(golden, tmp_path):
    source = golden["rotated_text.pdf"]
    _, target, output, result = edit(source, tmp_path, "Rotated label", "Rotated title")
    check_valid(source, output, result)
    edited = find(scene(output), "Rotated title")
    assert edited.style["rotation_deg"] == target.style["rotation_deg"] == 90.0
    assert abs(edited.content["baseline_origin"][0] - target.content["baseline_origin"][0]) < 0.05


def test_base14_font_replacement(golden, tmp_path):
    source = golden["base14_text.pdf"]
    _, _, output, result = edit(source, tmp_path, "Plain Helvetica text", "Edited Helvetica text")
    check_valid(source, output, result)
    assert "Edited Helvetica text" in texts(scene(output))


def test_delete_and_add_text(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    before = scene(source)
    target = find(before, "GSTIN:")
    output = tmp_path / "out.pdf"
    result = apply_batch(source, output, [
        {"type": "delete_object", "page_index": 0, "target_ids": [target.id]},
        {"type": "add_text", "page_index": 0, "payload": {"text": "PAID", "position": [400, 760],
                                                          "style": {"size_pt": 20, "fill": "#cc0000", "bold": True}}},
    ], lambda i: before)
    check_valid(source, output, result)
    after = texts(scene(output))
    assert "GSTIN:" not in after and "PAID" in after


def test_page_operations(golden, tmp_path):
    source = golden["multipage.pdf"]
    output = tmp_path / "pages.pdf"
    result = apply_batch(source, output, [
        {"type": "rotate_page", "page_index": 0, "payload": {"degrees": 90}},
        {"type": "reorder_page", "page_index": 0, "payload": {"to": 2}},
        {"type": "insert_page", "payload": {"at": 0}},
        {"type": "delete_page", "page_index": 1},
    ], lambda i: scene(source, i))
    assert result.page_order == [None, 2, 0]
    with fitz.open(output) as doc:
        assert doc.page_count == 3 and doc[2].rotation == 90 and not doc[0].get_text().strip()


def test_reconcile_preserves_ids_for_unchanged_and_edited_objects(golden, tmp_path):
    source = golden["simple_invoice.pdf"]
    before, target, output, result = edit(source, tmp_path, "4553.00", "4593.00")
    with fitz.open(output) as doc:
        raw_after = analyze_page(doc, 0, "00000000-0000-4000-8000-000000000000")
    after = reconcile(before, raw_after, {target.id: {"text": "4593.00", "bbox": result.outcomes[0].new_bbox}})
    assert find(after, "4593.00").id == target.id
    assert find(after, "VISHNU MEDICAL HALL").id == find(before, "VISHNU MEDICAL HALL").id
    assert len({o.id for o in after.objects}) == len(after.objects)
