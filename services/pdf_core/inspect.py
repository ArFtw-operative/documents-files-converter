"""Upload inspection / lightweight preflight (architecture §44.1, §89A.3, §89A.14, §89B.2).

Nothing found here is ever executed; the results drive warnings and editing guards.
"""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf as fitz

_ACTION_PATTERNS = {
    "javascript": re.compile(rb"/(JS|JavaScript)\b"),
    "launch_action": re.compile(rb"/Launch\b"),
    "external_reference": re.compile(rb"/(GoToR|GoToE|ImportData|SubmitForm)\b"),
}


def inspect_pdf(path: Path, max_xrefs_scanned: int = 200_000) -> dict:
    with fitz.open(path) as doc:
        info: dict = {
            "encrypted": bool(doc.needs_pass),
            "page_count": 0 if doc.needs_pass else doc.page_count,
            "repaired": bool(doc.is_repaired),
        }
        if doc.needs_pass:
            return info
        info["signed"] = doc.get_sigflags() > 0
        info["has_forms"] = bool(doc.is_form_pdf)
        info["embedded_files"] = doc.embfile_count()
        info["metadata"] = {k: v for k, v in (doc.metadata or {}).items() if v and k != "encryption"}
        findings: set[str] = set()
        for xref in range(1, min(doc.xref_length(), max_xrefs_scanned)):
            try:
                source = doc.xref_object(xref, compressed=True).encode("latin-1", "replace")
            except Exception:  # noqa: BLE001 - damaged objects are reported by qpdf instead
                continue
            for name, pattern in _ACTION_PATTERNS.items():
                if name not in findings and pattern.search(source):
                    findings.add(name)
        info["active_content"] = sorted(findings)
        return info
