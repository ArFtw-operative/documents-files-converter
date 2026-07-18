import fitz

from convertvault.pdf_scene import build_page_scene, interpret_document


def make_scene_pdf(path):
    document = fitz.open()
    page = document.new_page(width=400, height=500)
    page.insert_text((40, 60), "Editable native text", fontsize=13, color=(0.1, 0.2, 0.3))
    page.draw_rect(fitz.Rect(40, 90, 180, 140), color=(0, 0.4, 0), fill=(0.8, 1, 0.8))
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 12, 12), False)
    pixmap.clear_with(0x176B4D)
    page.insert_image(fitz.Rect(220, 40, 280, 100), stream=pixmap.tobytes("png"))
    page.add_text_annot((40, 170), "A standards annotation")
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(40, 210, 180, 230), "uri": "https://example.com"})
    widget = fitz.Widget(); widget.field_name = "customer"; widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(40, 250, 220, 280); widget.field_value = "Name"; page.add_widget(widget)
    document.set_toc([[1, "Start", 1]])
    document.embfile_add("notes.txt", b"Local attachment", filename="notes.txt", desc="Notes")
    document.save(path)


def test_document_interpretation_and_scene_graph_are_structured_and_stable(tmp_path):
    source = tmp_path / "scene.pdf"
    make_scene_pdf(source)

    model = interpret_document(source)
    assert model["page_count"] == 1
    assert model["bookmarks"][0][1] == "Start"
    assert model["attachments"][0]["name"] == "notes.txt"
    assert model["pages"][0]["form_field_count"] == 1

    session_id = "11111111-1111-4111-8111-111111111111"
    scene = build_page_scene(source, session_id, 1)
    repeated = build_page_scene(source, session_id, 1)
    assert [item["id"] for item in scene["objects"]] == [item["id"] for item in repeated["objects"]]
    assert len({item["id"] for item in scene["objects"]}) == len(scene["objects"])
    assert {item["type"] for item in scene["objects"]} >= {
        "text_run", "image", "vector_path", "annotation", "form_field", "link"
    }
    text = next(item for item in scene["objects"] if item["type"] == "text_run")
    assert text["text"] == "Editable native text"
    assert text["characters"][0]["unicode"] == "E"
    assert text["source"]["content_streams"]
    assert text["style"]["font_size"] == 13
    assert text["editability"] in {"Fully editable", "Editable with reconstruction"}

    another = build_page_scene(source, "22222222-2222-4222-8222-222222222222", 1)
    assert scene["objects"][0]["id"] != another["objects"][0]["id"]
