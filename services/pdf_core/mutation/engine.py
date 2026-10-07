"""Operation batch application (architecture §23, §54, §89B.4).

The engine never writes in place: it reads ``source`` and writes ``output`` (a temporary path chosen
by the caller), which is validated before the caller atomically promotes it to a revision.

Content operations address pages by their index in ``source``. Structural page operations run after
all content operations in the batch, in order, so indices in a batch are never ambiguous.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz

from ..fonts.resolver import FontResolver
from ..scene import PageScene
from .errors import MutationError
from .text import EditOutcome, add_text, delete_text, replace_text

CONTENT_OPERATIONS = {"replace_text", "add_text", "delete_object"}
PAGE_OPERATIONS = {"rotate_page", "delete_page", "reorder_page", "insert_page"}
SUPPORTED_OPERATIONS = CONTENT_OPERATIONS | PAGE_OPERATIONS


@dataclass
class BatchResult:
    page_order: list[int | None]  # new index -> source index (None = inserted page)
    changed_pages: set[int] = field(default_factory=set)  # source indices with any change
    rotated_pages: set[int] = field(default_factory=set)  # source indices whose /Rotate changed
    outcomes: list[EditOutcome] = field(default_factory=list)

    @property
    def regions(self) -> dict[int, list[list[float]]]:
        regions: dict[int, list[list[float]]] = {}
        for outcome in self.outcomes:
            if outcome.region:
                regions.setdefault(outcome.page_index, []).append(outcome.region)
        return regions

    @property
    def warnings(self) -> list[str]:
        return sorted({w for o in self.outcomes for w in o.warnings})


def _target(scene: PageScene, operation: dict):
    ids = operation.get("target_ids") or []
    if len(ids) != 1:
        raise MutationError("invalid_payload", "Exactly one target object is required.")
    target = scene.by_id(ids[0])
    if target is None:
        raise MutationError("target_not_found", "The selected object no longer exists.", {"target_id": ids[0]})
    return target


def apply_batch(source: Path, output: Path, operations: list[dict],
                scene_for: Callable[[int], PageScene], allow_signed: bool = False) -> BatchResult:
    for operation in operations:
        if operation.get("type") not in SUPPORTED_OPERATIONS:
            raise MutationError("unsupported_operation", f"Unsupported operation: {operation.get('type')}")
    document = fitz.open(source)
    try:
        if document.needs_pass:
            raise MutationError("encrypted", "Unlock this PDF before editing.")
        if document.get_sigflags() > 0 and not allow_signed:
            raise MutationError("signed_document", "Editing will invalidate this document's digital "
                                "signature. Confirm to continue; the signed original is preserved.")
        resolver = FontResolver(document)
        result = BatchResult(page_order=list(range(document.page_count)))
        content = [op for op in operations if op["type"] in CONTENT_OPERATIONS]
        structure = [op for op in operations if op["type"] in PAGE_OPERATIONS]
        for operation in content:
            index = int(operation.get("page_index", -1))
            if not 0 <= index < document.page_count:
                raise MutationError("invalid_payload", "The page does not exist.")
            payload = operation.get("payload") or {}
            kind = operation["type"]
            if kind == "replace_text":
                scene = scene_for(index)
                outcome = replace_text(document, resolver, scene, _target(scene, operation), payload)
            elif kind == "delete_object":
                scene = scene_for(index)
                outcome = delete_text(document, scene, _target(scene, operation))
            else:
                outcome = add_text(document, resolver, index, payload)
            result.outcomes.append(outcome)
            result.changed_pages.add(index)
        for operation in structure:
            _page_operation(document, result, operation)
        if document.page_count == 0:
            raise MutationError("invalid_payload", "A document must keep at least one page.")
        document.save(output, garbage=3, deflate=True)
        return result
    finally:
        document.close()


def _page_operation(document: fitz.Document, result: BatchResult, operation: dict) -> None:
    payload = operation.get("payload") or {}
    kind = operation["type"]
    index = int(operation.get("page_index", payload.get("page_index", -1)))
    count = document.page_count
    if kind == "insert_page":
        at = int(payload.get("at", count))
        if not 0 <= at <= count:
            raise MutationError("invalid_payload", "Insert position is outside the document.")
        reference = document[min(at, count - 1)].rect if count else fitz.paper_rect("a4")
        width = float(payload.get("width_pt") or reference.width)
        height = float(payload.get("height_pt") or reference.height)
        document.new_page(pno=at, width=width, height=height)
        result.page_order.insert(at, None)
        return
    if not 0 <= index < count:
        raise MutationError("invalid_payload", "The page does not exist.")
    if kind == "rotate_page":
        degrees = int(payload.get("degrees", 90))
        if degrees % 90:
            raise MutationError("invalid_payload", "Rotation must be a multiple of 90 degrees.")
        page = document[index]
        page.set_rotation((page.rotation + degrees) % 360)
        source_index = result.page_order[index]
        if source_index is not None:
            result.changed_pages.add(source_index)
            result.rotated_pages.add(source_index)
    elif kind == "delete_page":
        if count == 1:
            raise MutationError("invalid_payload", "A document must keep at least one page.")
        document.delete_page(index)
        result.page_order.pop(index)
    elif kind == "reorder_page":
        to = int(payload.get("to", -1))
        if not 0 <= to < count:
            raise MutationError("invalid_payload", "Destination page is outside the document.")
        if to == index:
            return
        # PyMuPDF move_page inserts *before* the given page number; -1 appends.
        if to < index:
            document.move_page(index, to)
        else:
            document.move_page(index, to + 1 if to + 1 < count else -1)
        moved = result.page_order.pop(index)
        result.page_order.insert(to, moved)
