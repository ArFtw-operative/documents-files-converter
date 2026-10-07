"""Persist and load Document Scene Graph pages (architecture §8, §26 scene_objects)."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pdf_core.scene import PageScene, SceneObject

from ..models import PageVersion, SceneObjectRow


def store_scene(db: Session, version: PageVersion, scene: PageScene) -> None:
    db.execute(delete(SceneObjectRow).where(SceneObjectRow.page_version_id == version.id))
    for obj in scene.objects:
        db.add(SceneObjectRow(
            page_version_id=version.id, object_id=obj.id, object_type=obj.type.value, source=obj.source.value,
            bbox=obj.bbox, polygon=obj.quad, transform=obj.transform, style=obj.style, content=obj.content,
            text=obj.content.get("text"), confidence=obj.confidence, z_index=obj.z_index,
            native_ref=obj.native_ref, logical_group_id=obj.logical_group_id, editable=obj.editable,
        ))
    version.width_pt, version.height_pt = scene.width_pt, scene.height_pt
    version.rotation, version.view_box = scene.rotation, scene.view_box
    version.page_type = scene.page_type.value
    version.analyzer_version = scene.analyzer_version
    version.warnings = scene.warnings
    version.analysis_status = "ready"


def load_scene(db: Session, version: PageVersion, page_index: int) -> PageScene | None:
    if version.analysis_status != "ready":
        return None
    rows = db.scalars(select(SceneObjectRow).where(SceneObjectRow.page_version_id == version.id)
                      .order_by(SceneObjectRow.pk)).all()
    objects = [SceneObject(
        id=row.object_id, type=row.object_type, source=row.source, bbox=row.bbox, quad=row.polygon,
        transform=row.transform, z_index=row.z_index, confidence=row.confidence, style=row.style,
        content=row.content, native_ref=row.native_ref, logical_group_id=row.logical_group_id,
        editable=row.editable,
    ) for row in rows]
    return PageScene(
        page_index=page_index, width_pt=version.width_pt or 0, height_pt=version.height_pt or 0,
        rotation=version.rotation or 0, view_box=version.view_box or [0, 0, 0, 0],
        page_type=version.page_type or "EMPTY", analyzer_version=version.analyzer_version or "",
        objects=objects, warnings=version.warnings or [],
    )


def public_scene(scene: PageScene, page_id: str, version: int, diagnostics: bool = False) -> dict:
    """Scene payload for the browser. Raw PDF references are developer diagnostics only (§87)."""
    data = scene.model_dump(mode="json")
    data["page_id"] = page_id
    data["page_version"] = version
    if not diagnostics:
        for obj in data["objects"]:
            obj.pop("native_ref", None)
            obj["style"].pop("font_key", None)
            obj["style"].pop("fill_components", None)
    return data
