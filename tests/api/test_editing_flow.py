"""End-to-end API: upload → scene → in-place edit → validate → undo/redo → export, with
per-user isolation, CSRF and revision conflict handling."""

import uuid

import pymupdf as fitz
import pytest
from fastapi.testclient import TestClient

from folio.main import app

ADMIN = {"email": "admin@folio.test", "password": "correct horse battery", "display_name": "Admin"}


class Client:
    def __init__(self) -> None:
        self.http = TestClient(app)
        self.csrf = None

    def _headers(self) -> dict:
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, url, **kw):
        return self.http.get(url, **kw)

    def post(self, url, **kw):
        response = self.http.post(url, headers={**self._headers(), **kw.pop("headers", {})}, **kw)
        if response.status_code < 300 and response.headers.get("content-type", "").startswith("application/json"):
            body = response.json()
            if isinstance(body, dict) and body.get("csrf_token"):
                self.csrf = body["csrf_token"]
        return response

    def patch(self, url, **kw):
        return self.http.patch(url, headers=self._headers(), **kw)

    def delete(self, url, **kw):
        return self.http.delete(url, headers=self._headers(), **kw)


@pytest.fixture(scope="module")
def admin() -> Client:
    client = Client()
    state = client.get("/api/v1/auth/state").json()
    if state["setup_required"]:
        assert client.post("/api/v1/auth/setup", json=ADMIN).status_code == 201
    else:
        assert client.post("/api/v1/auth/login", json={"email": ADMIN["email"], "password": ADMIN["password"]}).status_code == 200
    return client


@pytest.fixture(scope="module")
def document(admin, golden) -> dict:
    with golden["simple_invoice.pdf"].open("rb") as handle:
        response = admin.post("/api/v1/documents", files={"file": ("invoice.pdf", handle, "application/pdf")})
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["status"] == "ready" and doc["page_count"] == 1 and doc["current_revision"] == 1
    return doc


def scene(client, doc_id, page_id, revision=None):
    url = f"/api/v1/documents/{doc_id}/pages/{page_id}/scene"
    response = client.get(url, params={"revision": revision} if revision else None)
    assert response.status_code == 200, response.text
    return response.json()


def text_object(page_scene, text):
    return next(o for o in page_scene["objects"] if o["type"] == "TEXT_NATIVE" and o["content"]["text"] == text)


def ops(client, doc_id, base, operations):
    return client.post(f"/api/v1/documents/{doc_id}/operations",
                       json={"base_revision": base, "client_batch_id": uuid.uuid4().hex, "operations": operations})


def pdf_text(client, doc_id, revision) -> str:
    response = client.get(f"/api/v1/documents/{doc_id}/revisions/{revision}/file")
    assert response.status_code == 200
    with fitz.open(stream=response.content, filetype="pdf") as pdf:
        return pdf[0].get_text()


def test_vertical_slice_edit_undo_redo(admin, document):
    doc_id, page_id = document["id"], document["pages"][0]["page_id"]
    page = scene(admin, doc_id, page_id)
    amount = text_object(page, "4553.00")
    assert "native_ref" not in amount  # internals stay out of the normal UI payload (§84)
    assert len(amount["content"]["glyphs"]) == 7

    response = ops(admin, doc_id, 1, [{"type": "replace_text", "page_id": page_id, "target_ids": [amount["id"]],
                                       "payload": {"old_text": "4553.00", "new_text": "4593.00"}}])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "committed" and body["revision"] == 2
    assert "4593.00" in pdf_text(admin, doc_id, 2) and "4553.00" not in pdf_text(admin, doc_id, 2)

    edited = scene(admin, doc_id, page_id)
    assert text_object(edited, "4593.00")["id"] == amount["id"]  # stable identity (§55)

    undo = admin.post(f"/api/v1/documents/{doc_id}/undo", json={"expected_revision": 2})
    assert undo.status_code == 200 and undo.json()["revision"] == 3
    revisions = {r["revision"]: r for r in admin.get(f"/api/v1/documents/{doc_id}/revisions").json()}
    assert revisions[3]["sha256"] == revisions[1]["sha256"]  # original appearance returns exactly
    assert text_object(scene(admin, doc_id, page_id), "4553.00")["id"] == amount["id"]

    redo = admin.post(f"/api/v1/documents/{doc_id}/redo", json={"expected_revision": 3})
    assert redo.status_code == 200 and redo.json()["revision"] == 4
    revisions = {r["revision"]: r for r in admin.get(f"/api/v1/documents/{doc_id}/revisions").json()}
    assert revisions[4]["sha256"] == revisions[2]["sha256"]
    detail = admin.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["can_undo"] and not detail["can_redo"]


def test_stale_edit_of_changed_text_conflicts_but_unrelated_edit_rebases(admin, document):
    doc_id, page_id = document["id"], document["pages"][0]["page_id"]
    current = admin.get(f"/api/v1/documents/{doc_id}").json()["current_revision"]
    page = scene(admin, doc_id, page_id, revision=1)
    amount = text_object(page, "4553.00")
    stale = ops(admin, doc_id, 1, [{"type": "replace_text", "page_id": page_id, "target_ids": [amount["id"]],
                                    "payload": {"old_text": "4553.00", "new_text": "1.00"}}])
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "target_modified"
    assert stale.json()["error"]["details"]["current_revision"] == current

    gstin = text_object(page, "32ABCDE1234F1Z5")
    rebased = ops(admin, doc_id, 1, [{"type": "replace_text", "page_id": page_id, "target_ids": [gstin["id"]],
                                      "payload": {"old_text": "32ABCDE1234F1Z5", "new_text": "32ABCDE1234F1Z6"}}])
    assert rebased.status_code == 200, rebased.text
    assert rebased.json()["revision"] == current + 1


def test_overflow_needs_confirmation(admin, document):
    doc_id, page_id = document["id"], document["pages"][0]["page_id"]
    detail = admin.get(f"/api/v1/documents/{doc_id}").json()
    item = text_object(scene(admin, doc_id, page_id), "Vitamin C")
    response = ops(admin, doc_id, detail["current_revision"], [{
        "type": "replace_text", "page_id": page_id, "target_ids": [item["id"]],
        "payload": {"old_text": "Vitamin C", "new_text": "Vitamin C chewable tablets 500 mg orange flavour, pack of 60, sugar free, store in a cool dry place"}}])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "needs_confirmation"


def test_idempotent_replay(admin, document):
    doc_id, page_id = document["id"], document["pages"][0]["page_id"]
    detail = admin.get(f"/api/v1/documents/{doc_id}").json()
    item = text_object(scene(admin, doc_id, page_id), "Paracetamol 500mg")
    payload = {"base_revision": detail["current_revision"], "client_batch_id": "replay-" + uuid.uuid4().hex,
               "operations": [{"type": "replace_text", "page_id": page_id, "target_ids": [item["id"]],
                               "payload": {"old_text": "Paracetamol 500mg", "new_text": "Paracetamol 650mg"}}]}
    first = admin.post(f"/api/v1/documents/{doc_id}/operations", json=payload).json()
    second = admin.post(f"/api/v1/documents/{doc_id}/operations", json=payload).json()
    assert first["operation_batch_id"] == second["operation_batch_id"] and first["revision"] == second["revision"]


def test_export_and_audit(admin, document):
    doc_id = document["id"]
    export = admin.post(f"/api/v1/documents/{doc_id}/exports", json={"mode": "standard"})
    assert export.status_code == 202 and export.json()["status"] == "ready", export.text
    file = admin.get(f"/api/v1/documents/{doc_id}/exports/{export.json()['id']}/file")
    assert file.status_code == 200 and file.content.startswith(b"%PDF")
    log = admin.get("/api/v1/admin/audit").json()
    edit = next(row for row in log if row["action"] == "document.replace_text")
    assert {"old_text", "new_text", "revision_before", "revision_after"} <= set(edit["details"])


def test_csrf_required(admin, document):
    response = admin.http.post(f"/api/v1/documents/{document['id']}/undo", json={})
    assert response.status_code == 403


def test_users_are_isolated(admin, document):
    created = admin.post("/api/v1/admin/users", json={"email": "bob@folio.test", "display_name": "Bob",
                                                      "password": "another long secret"})
    assert created.status_code == 201, created.text
    bob = Client()
    assert bob.post("/api/v1/auth/login", json={"email": "bob@folio.test", "password": "another long secret"}).status_code == 200
    doc_id, page_id = document["id"], document["pages"][0]["page_id"]
    assert bob.get("/api/v1/documents").json()["documents"] == []
    for url in (f"/api/v1/documents/{doc_id}", f"/api/v1/documents/{doc_id}/revisions/1/file",
                f"/api/v1/documents/{doc_id}/pages/{page_id}/scene", f"/api/v1/documents/{doc_id}/revisions"):
        assert bob.get(url).status_code == 404, url
    assert bob.post(f"/api/v1/documents/{doc_id}/undo", json={}).status_code == 404
    assert ops(bob, doc_id, 1, [{"type": "rotate_page", "page_id": page_id}]).status_code == 404
    assert bob.get("/api/v1/admin/users").status_code == 403


def test_login_lockout(admin):
    client = Client()
    for _ in range(8):
        assert client.post("/api/v1/auth/login", json={"email": "bob@folio.test", "password": "wrong password!"}).status_code == 401
    locked = client.post("/api/v1/auth/login", json={"email": "bob@folio.test", "password": "another long secret"})
    assert locked.status_code == 401 and "Too many" in locked.json()["detail"]


def test_rejects_non_pdf(admin):
    response = admin.post("/api/v1/documents", files={"file": ("x.pdf", b"not a pdf at all", "application/pdf")})
    assert response.status_code == 415
