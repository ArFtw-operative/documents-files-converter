from io import BytesIO
import fitz
from fastapi.testclient import TestClient
from PIL import Image
from convertvault.main import app
from convertvault.database import SessionLocal
from convertvault.models import Job, JobStatus, StoredFile
from convertvault.tasks import run_conversion


def test_setup_upload_library_and_authorization(monkeypatch):
    with TestClient(app) as client:
        preflight = client.options("/api/v1/pdf/projects/example", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "authorization,content-type",
        })
        assert preflight.status_code == 200
        assert "PUT" in preflight.headers["access-control-allow-methods"]
        assert client.get("/api/v1/setup/status").json()["required"] is True
        created = client.post("/api/v1/setup", json={
            "email": "admin@example.com", "display_name": "Vault Admin", "password": "correct horse battery staple"
        })
        assert created.status_code == 201
        token = created.json()["access_token"]
        refresh_token = created.json()["refresh_token"]
        headers = {"Authorization": f"Bearer {token}"}
        image = BytesIO(); Image.new("RGB", (16, 16), "green").save(image, "PNG"); image.seek(0)
        uploaded = client.post("/api/v1/files", headers=headers, files={"file": ("safe.png", image, "image/png")})
        assert uploaded.status_code == 201
        file_id = uploaded.json()["id"]
        listing = client.get("/api/v1/files", headers=headers).json()
        assert listing["total"] == 1 and listing["items"][0]["id"] == file_id
        assert client.get(f"/api/v1/files/{file_id}/download").status_code == 401
        downloaded = client.get(f"/api/v1/files/{file_id}/download", headers=headers)
        assert downloaded.status_code == 200 and downloaded.content.startswith(b"\x89PNG")
        caps = client.get("/api/v1/capabilities", headers=headers).json()["items"]
        assert any(item["operation"] == "image.convert" for item in caps)
        folder = client.post("/api/v1/folders", headers=headers, json={"name": "Receipts"})
        assert folder.status_code == 201
        moved = client.patch(f"/api/v1/files/{file_id}", headers=headers,
                             json={"folder_id": folder.json()["id"], "display_name": "renamed.png", "is_favorite": True})
        assert moved.status_code == 200 and moved.json()["is_favorite"] is True
        tag = client.post("/api/v1/tags", headers=headers, json={"name": "Important", "color": "#176b4d"})
        assert tag.status_code == 201
        tagged = client.post(f"/api/v1/files/{file_id}/tags/{tag.json()['id']}", headers=headers)
        assert tagged.status_code == 200 and tagged.json()["tags"][0]["name"] == "Important"
        filtered = client.get(f"/api/v1/files?tag_id={tag.json()['id']}&favorite=true", headers=headers).json()
        assert filtered["total"] == 1
        assert client.post(f"/api/v1/files/{file_id}/shares", headers=headers, json={"expires_in_hours": 1}).status_code == 403
        rejected = client.post("/api/v1/files", headers=headers, files={"file": ("malware.exe", b"MZpayload", "application/octet-stream")})
        assert rejected.status_code == 415

        with SessionLocal() as db:
            source = db.get(StoredFile, file_id)
            job = Job(owner_id=source.owner_id, input_file_id=file_id, operation="image.convert",
                      target_format="jpg", options={"quality": 75})
            db.add(job); db.commit(); job_id = job.id
        run_conversion.run(job_id)
        with SessionLocal() as db:
            completed = db.get(Job, job_id)
            output = db.get(StoredFile, completed.output_file_id)
            assert completed.status == JobStatus.succeeded
            assert output.parent_file_id == file_id and output.extension == "jpg"
            output_id = output.id
        result = client.get(f"/api/v1/files/{output.id}/download", headers=headers)
        assert result.status_code == 200 and result.content.startswith(b"\xff\xd8")
        timeline = client.get(f"/api/v1/files/{output_id}/versions", headers=headers).json()
        assert timeline["root_id"] == file_id and len(timeline["items"]) == 2
        disabled = client.put("/api/v1/admin/capabilities/image.convert?enabled=false", headers=headers)
        assert disabled.status_code == 200
        assert not any(item["operation"] == "image.convert" for item in client.get("/api/v1/capabilities", headers=headers).json()["items"])
        blocked_job = client.post("/api/v1/jobs", headers=headers, json={
            "input_file_id": file_id, "operation": "image.convert", "target_format": "jpg", "options": {}
        })
        assert blocked_job.status_code == 403
        assert client.put("/api/v1/admin/capabilities/image.convert?enabled=true", headers=headers).status_code == 200
        assert client.patch(f"/api/v1/admin/users/{created.json()['user']['id']}", headers=headers,
                            json={"is_active": False}).status_code == 409
        assert client.get("/api/v1/admin/fonts", headers=headers).status_code == 200

        pdf_document = fitz.open()
        pdf_page = pdf_document.new_page(width=400, height=500)
        pdf_page.insert_text((40, 60), "Confidential draft")
        pdf_pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 20), False)
        pdf_pixmap.clear_with(0x176B4D)
        pdf_page.insert_image(fitz.Rect(250, 35, 320, 105), stream=pdf_pixmap.tobytes("png"))
        pdf_page.draw_rect(fitz.Rect(40, 150, 140, 205), color=(0.1, 0.4, 0.2),
                           fill=(0.8, 0.95, 0.85), width=2)
        pdf_bytes = pdf_document.tobytes()
        pdf_document.close()
        uploaded_pdf = client.post(
            "/api/v1/files",
            headers=headers,
            files={"file": ("contract.pdf", pdf_bytes, "application/pdf")},
        )
        assert uploaded_pdf.status_code == 201
        imported_document = fitz.open()
        imported_page = imported_document.new_page(width=320, height=420)
        imported_page.insert_text((35, 55), "Imported appendix page")
        imported_bytes = imported_document.tobytes(); imported_document.close()
        imported_pdf = client.post(
            "/api/v1/files", headers=headers,
            files={"file": ("appendix.pdf", imported_bytes, "application/pdf")},
        )
        assert imported_pdf.status_code == 201
        comparison = client.post(
            "/api/v1/pdf/compare", headers=headers,
            json={"before_file_id": uploaded_pdf.json()["id"], "after_file_id": imported_pdf.json()["id"],
                  "ignore_headers_footers": False, "ignore_formatting": False, "ignore_whitespace": True},
        )
        assert comparison.status_code == 200 and comparison.json()["text_aware"] is True
        assert comparison.json()["summary"]["total"] > 0
        overlay = client.get(
            "/api/v1/pdf/compare/render", headers=headers,
            params={"before_file_id": uploaded_pdf.json()["id"], "after_file_id": imported_pdf.json()["id"],
                    "side": "overlay", "page": 1, "dpi": 72},
        )
        assert overlay.status_code == 200 and overlay.content.startswith(b"\x89PNG")
        project_response = client.post(
            "/api/v1/pdf/projects",
            headers=headers,
            json={"file_id": uploaded_pdf.json()["id"], "name": "Contract editing"},
        )
        assert project_response.status_code == 201
        project = project_response.json()
        inspected = client.get(
            f"/api/v1/pdf/projects/{project['id']}/document", headers=headers
        )
        assert inspected.status_code == 200 and inspected.json()["page_count"] == 1
        rendered = client.get(
            f"/api/v1/pdf/projects/{project['id']}/pages/1/render?dpi=72",
            headers=headers,
        )
        assert rendered.status_code == 200 and rendered.content.startswith(b"\x89PNG")
        saved = client.put(
            f"/api/v1/pdf/projects/{project['id']}",
            headers=headers,
            json={
                "expected_revision": 0,
                "operations": [
                    {
                        "kind": "content.replace_text",
                        "page": 1,
                        "text": "Confidential draft",
                        "replacement": "Approved contract",
                    },
                    {
                        "kind": "annotate.comment",
                        "page": 1,
                        "rect": [40, 90, 70, 120],
                        "text": "Reviewed locally",
                    },
                ],
            },
        )
        assert saved.status_code == 200 and saved.json()["revision"] == 1
        conflict = client.put(
            f"/api/v1/pdf/projects/{project['id']}",
            headers=headers,
            json={"expected_revision": 0, "operations": []},
        )
        assert conflict.status_code == 409
        monkeypatch.setattr(run_conversion, "apply_async", lambda *args, **kwargs: None)
        published = client.post(
            f"/api/v1/pdf/projects/{project['id']}/publish", headers=headers
        )
        assert published.status_code == 202
        run_conversion.run(published.json()["id"])
        with SessionLocal() as db:
            pdf_job = db.get(Job, published.json()["id"])
            edited_file = db.get(StoredFile, pdf_job.output_file_id)
            assert pdf_job.status == JobStatus.succeeded
        edited = client.get(
            f"/api/v1/files/{edited_file.id}/download", headers=headers
        )
        with fitz.open(stream=edited.content, filetype="pdf") as result_document:
            assert "Approved contract" in result_document[0].get_text()
            assert "Confidential draft" not in result_document[0].get_text()

        workspace_document = client.post(
            "/api/v1/pdf/documents",
            headers=headers,
            json={"file_id": uploaded_pdf.json()["id"], "name": "Contract workspace"},
        )
        assert workspace_document.status_code == 201
        document_id = workspace_document.json()["id"]
        document_model = client.get(f"/api/v1/pdf/documents/{document_id}/model", headers=headers)
        assert document_model.status_code == 200 and document_model.json()["page_count"] == 1
        session_response = client.post(
            f"/api/v1/pdf/documents/{document_id}/sessions", headers=headers, json={}
        )
        assert session_response.status_code == 201
        session = session_response.json()
        page_import = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/pages/import", headers=headers,
            json={"expected_revision": 0, "idempotency_key": "import-page-001", "action": "insert",
                  "page": 2, "source_file_id": imported_pdf.json()["id"], "source_page": 1},
        )
        assert page_import.status_code == 201 and page_import.json()["session"]["revision"] == 1
        page_geometry = client.patch(
            f"/api/v1/pdf/sessions/{session['id']}/pages/1/geometry", headers=headers,
            json={"expected_revision": 1, "idempotency_key": "resize-page-001", "action": "resize",
                  "width": 450, "height": 550, "resize_mode": "fit"},
        )
        assert page_geometry.status_code == 200 and page_geometry.json()["session"]["revision"] == 2
        scene = client.get(f"/api/v1/pdf/sessions/{session['id']}/scene?page=1", headers=headers)
        assert scene.status_code == 200
        text_object = next(item for item in scene.json()["objects"] if item["type"] == "text_run")
        image_object = next(item for item in scene.json()["objects"] if item["type"] == "image")
        vector_object = next(item for item in scene.json()["objects"] if item["type"] == "vector_path")
        command_payload = {
            "expected_revision": 2,
            "idempotency_key": "edit-contract-001",
            "operation": "replace_range",
            "range": {"start": 0, "end": len("Confidential draft")},
            "text": "Approved contract",
            "reflow_policy": "preserve_line_positions",
            "font_policy": "preserve_or_prompt",
        }
        command = client.patch(
            f"/api/v1/pdf/sessions/{session['id']}/text/{text_object['id']}", headers=headers, json=command_payload
        )
        assert command.status_code == 200
        assert command.json()["session"]["revision"] == 3
        replay = client.patch(
            f"/api/v1/pdf/sessions/{session['id']}/text/{text_object['id']}", headers=headers, json=command_payload
        )
        assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True
        conflict = client.patch(
            f"/api/v1/pdf/sessions/{session['id']}/text/{text_object['id']}",
            headers=headers,
            json={**command_payload, "idempotency_key": "edit-contract-002"},
        )
        assert conflict.status_code == 409
        undone = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/undo", headers=headers,
            json={"expected_revision": 3, "idempotency_key": "undo-contract-001"},
        )
        assert undone.status_code == 200 and len(undone.json()["session"]["operations"]) == 2
        redone = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/redo", headers=headers,
            json={"expected_revision": 4, "idempotency_key": "redo-contract-001"},
        )
        assert redone.status_code == 200 and len(redone.json()["session"]["operations"]) == 3
        image_edit = client.patch(
            f"/api/v1/pdf/sessions/{session['id']}/images/{image_object['id']}", headers=headers,
            json={"expected_revision": 5, "idempotency_key": "move-image-001", "action": "transform",
                  "rect": [230, 250, 360, 370], "rotation": 31, "crop": [0.1, 0.1, 0.9, 0.9]},
        )
        assert image_edit.status_code == 200 and image_edit.json()["session"]["revision"] == 6
        vector_edit = client.patch(
            f"/api/v1/pdf/sessions/{session['id']}/vectors/{vector_object['id']}", headers=headers,
            json={"expected_revision": 6, "idempotency_key": "move-vector-001", "action": "transform",
                  "rect": [40, 300, 190, 390], "rotation": 17, "color": "#123456",
                  "fill": "#dceeff", "width": 4, "opacity": 0.8},
        )
        assert vector_edit.status_code == 200 and vector_edit.json()["session"]["revision"] == 7
        annotation = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/annotations", headers=headers,
            json={"expected_revision": 7, "idempotency_key": "annot-comment-api-001",
                  "operation": {"kind": "annotate.comment", "page": 1,
                                "rect": [55, 410, 85, 440], "text": "Review this clause",
                                "author": "Legal reviewer", "subject": "Contract review",
                                "color": "#176b4d", "opacity": 0.8, "annotation_status": "open"}},
        )
        assert annotation.status_code == 201 and annotation.json()["session"]["revision"] == 8
        annotation_name = "annot-annot-comment-api-001"
        annotations = client.get(
            f"/api/v1/pdf/sessions/{session['id']}/annotations?author=Legal&type=Text&status=open",
            headers=headers,
        )
        assert annotations.status_code == 200 and annotations.json()["total"] == 1
        assert annotations.json()["items"][0]["id"] == annotation_name
        reply = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/annotations/{annotation_name}/replies", headers=headers,
            json={"expected_revision": 8, "idempotency_key": "annot-reply-api-001",
                  "text": "Resolved in the latest wording", "author": "Document owner"},
        )
        assert reply.status_code == 201 and reply.json()["session"]["revision"] == 9
        updated = client.patch(
            f"/api/v1/pdf/sessions/{session['id']}/annotations/{annotation_name}", headers=headers,
            json={"expected_revision": 9, "idempotency_key": "annot-update-api-001",
                  "annotation_status": "accepted", "locked": True},
        )
        assert updated.status_code == 200 and updated.json()["session"]["revision"] == 10
        threaded = client.get(
            f"/api/v1/pdf/sessions/{session['id']}/annotations?search=wording&sort=newest", headers=headers
        ).json()
        assert threaded["total"] == 1 and threaded["items"][0]["parent_id"] == annotation_name
        hidden_resolved = client.get(
            f"/api/v1/pdf/sessions/{session['id']}/annotations?hide_resolved=true", headers=headers
        ).json()
        assert all(item["id"] != annotation_name for item in hidden_resolved["items"])
        reply_name = "reply-annot-reply-api-001"
        deleted = client.request(
            "DELETE", f"/api/v1/pdf/sessions/{session['id']}/annotations/{reply_name}", headers=headers,
            json={"expected_revision": 10, "idempotency_key": "annot-delete-api-001"},
        )
        assert deleted.status_code == 200 and deleted.json()["session"]["revision"] == 11
        form_command = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/commands", headers=headers,
            json={"expected_revision": 11, "idempotency_key": "form-country-api-001",
                  "operation": {"kind": "form.combo", "page": 1, "rect": [60, 470, 250, 505],
                                "field_name": "country", "field_label": "Country",
                                "field_value": "India", "choice_values": ["India", "United Kingdom"],
                                "required": True}},
        )
        assert form_command.status_code == 201 and form_command.json()["session"]["revision"] == 12
        form_inspection = client.get(f"/api/v1/pdf/sessions/{session['id']}/forms", headers=headers).json()
        assert form_inspection["valid"] is True
        assert any(field["name"] == "country" and field["type"] == "ComboBox" for field in form_inspection["items"])
        form_import = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/forms/data", headers=headers,
            json={"expected_revision": 12, "idempotency_key": "form-import-api-001",
                  "values": {"country": "United Kingdom"}},
        )
        assert form_import.status_code == 200 and form_import.json()["session"]["revision"] == 13
        form_json = client.get(f"/api/v1/pdf/sessions/{session['id']}/forms/data", headers=headers).json()
        assert form_json["values"]["country"] == "United Kingdom"
        form_csv = client.get(f"/api/v1/pdf/sessions/{session['id']}/forms/data?format=csv", headers=headers)
        assert form_csv.status_code == 200 and "country" in form_csv.text
        form_reset = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/forms/reset", headers=headers,
            json={"expected_revision": 13, "idempotency_key": "form-reset-api-001"},
        )
        assert form_reset.status_code == 200 and form_reset.json()["session"]["revision"] == 14
        bookmark_command = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/commands", headers=headers,
            json={"expected_revision": 14, "idempotency_key": "bookmark-api-001",
                  "operation": {"kind": "bookmark.add", "bookmark_title": "Contract page",
                                "bookmark_level": 1, "target_page": 1}},
        )
        assert bookmark_command.status_code == 201 and bookmark_command.json()["session"]["revision"] == 15
        attachment_command = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/commands", headers=headers,
            json={"expected_revision": 15, "idempotency_key": "attachment-api-001",
                  "operation": {"kind": "attachment.add", "attachment_file_id": file_id,
                                "attachment_name": "evidence.png", "text": "Embedded evidence"}},
        )
        assert attachment_command.status_code == 201 and attachment_command.json()["session"]["revision"] == 16
        navigation = client.get(f"/api/v1/pdf/sessions/{session['id']}/navigation", headers=headers).json()
        assert navigation["bookmarks"][0]["title"] == "Contract page"
        assert navigation["attachments"][0]["name"] == "evidence.png"
        embedded = client.get(
            f"/api/v1/pdf/sessions/{session['id']}/attachments/download", headers=headers,
            params={"name": "evidence.png"},
        )
        assert embedded.status_code == 200 and embedded.content.startswith(b"\x89PNG")
        attachment_delete = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/commands", headers=headers,
            json={"expected_revision": 16, "idempotency_key": "attachment-delete-api-001",
                  "operation": {"kind": "attachment.delete", "attachment_name": "evidence.png"}},
        )
        assert attachment_delete.status_code == 201 and attachment_delete.json()["session"]["revision"] == 17
        live_preview = client.get(
            f"/api/v1/pdf/sessions/{session['id']}/pages/1/render?dpi=96", headers=headers
        )
        assert live_preview.status_code == 200 and live_preview.content.startswith(b"\x89PNG")
        assert live_preview.headers["x-pdf-revision"] == "17"
        history = client.get(f"/api/v1/pdf/sessions/{session['id']}/commands", headers=headers).json()
        assert history["revision"] == 17 and len(history["items"]) == 17
        session_export = client.post(
            f"/api/v1/pdf/sessions/{session['id']}/exports", headers=headers,
            json={"expected_revision": 17, "idempotency_key": "export-contract-001"},
        )
        assert session_export.status_code == 202
        run_conversion.run(session_export.json()["id"])
        exported_job = client.get("/api/v1/jobs", headers=headers).json()["items"]
        exported_job = next(item for item in exported_job if item["id"] == session_export.json()["id"])
        assert exported_job["status"] == "succeeded"
        workspace_versions = client.get(
            f"/api/v1/pdf/documents/{document_id}/versions", headers=headers
        ).json()["items"]
        assert len(workspace_versions) == 2
        assert workspace_versions[0]["validation_report"]["valid"] is True

        rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert rotated.status_code == 200 and rotated.json()["refresh_token"] != refresh_token
        new_headers = {"Authorization": f"Bearer {rotated.json()['access_token']}"}
        assert client.post("/api/v1/auth/logout", headers=new_headers,
                           json={"refresh_token": rotated.json()["refresh_token"]}).status_code == 204
        assert client.get("/api/v1/auth/me", headers=new_headers).status_code == 401
