"""Stable object identity across page versions (architecture §55, §56)."""

from __future__ import annotations

from .scene import ObjectType, PageScene, SceneObject


def _iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _signature(obj: SceneObject) -> tuple:
    if obj.type == ObjectType.TEXT_NATIVE:
        return (obj.type, obj.content.get("text"), obj.style.get("font_name"), obj.style.get("size_pt"))
    return (obj.type,)


def reconcile(previous: PageScene | None, current: PageScene,
              edited: dict[str, dict] | None = None) -> PageScene:
    """Rewrite ``current`` object ids so unchanged objects keep their previous ids.

    ``edited`` maps a previous object id to ``{"text": new_text, "bbox": new_bbox}`` for objects an
    operation replaced; the replacement inherits the edited object's id.
    """
    if previous is None:
        return current
    assigned: dict[str, str] = {}  # current id -> previous id
    taken: set[str] = set()
    for old_id, hint in (edited or {}).items():
        best, score = None, 0.0
        for obj in current.objects:
            if obj.id in assigned or obj.type != ObjectType.TEXT_NATIVE:
                continue
            if obj.content.get("text") != hint.get("text"):
                continue
            overlap = _iou(obj.bbox, hint["bbox"]) if hint.get("bbox") else 0.5
            if overlap > score:
                best, score = obj, overlap
        if best is not None and score > 0.3:
            assigned[best.id] = old_id
            taken.add(old_id)
    by_signature: dict[tuple, list[SceneObject]] = {}
    for old in previous.objects:
        if old.id not in taken:
            by_signature.setdefault(_signature(old), []).append(old)
    for obj in current.objects:
        if obj.id in assigned:
            continue
        candidates = by_signature.get(_signature(obj), [])
        best, score = None, 0.0
        for old in candidates:
            if old.id in taken:
                continue
            overlap = _iou(obj.bbox, old.bbox)
            if overlap > score:
                best, score = old, overlap
        if best is not None and score >= 0.8:
            assigned[obj.id] = best.id
            taken.add(best.id)
    objects = []
    for obj in current.objects:
        new_id = assigned.get(obj.id)
        if new_id is None and obj.id in taken:
            # Deterministic id collides with a previous id now owned by another object.
            new_id = obj.id + "-n"
        objects.append(obj.model_copy(update={"id": new_id or obj.id}))
    return current.model_copy(update={"objects": objects})
