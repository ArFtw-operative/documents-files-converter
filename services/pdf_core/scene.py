"""Document Scene Graph contract (architecture §8).

All geometry is canonical PDF user space: points, bottom-left origin, unrotated page, the same
space PDF.js viewports transform from. Quads are 8 numbers ``[x0,y0, x1,y1, x2,y2, x3,y3]`` in the
order baseline-start-bottom, baseline-end-bottom, end-top, start-top so that the first edge always
runs along the writing direction.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

ANALYZER_VERSION = "native-1.0"


class ObjectType(StrEnum):
    TEXT_NATIVE = "TEXT_NATIVE"
    TEXT_OCR = "TEXT_OCR"
    TEXT_HANDWRITING = "TEXT_HANDWRITING"
    IMAGE = "IMAGE"
    PATH = "PATH"
    FORM_XOBJECT = "FORM_XOBJECT"
    INK_ANNOTATION = "INK_ANNOTATION"
    ANNOTATION_TEXT = "ANNOTATION_TEXT"
    ANNOTATION_HIGHLIGHT = "ANNOTATION_HIGHLIGHT"
    TABLE = "TABLE"
    TABLE_CELL = "TABLE_CELL"
    BARCODE = "BARCODE"
    SIGNATURE = "SIGNATURE"
    STAMP = "STAMP"
    REDACTION = "REDACTION"
    LINK = "LINK"
    UNKNOWN = "UNKNOWN"


class ObjectSource(StrEnum):
    PDF_NATIVE = "PDF_NATIVE"
    OCR_DERIVED = "OCR_DERIVED"
    VISION_DERIVED = "VISION_DERIVED"
    USER_CREATED = "USER_CREATED"
    ANNOTATION_NATIVE = "ANNOTATION_NATIVE"
    RASTER_RECONSTRUCTED = "RASTER_RECONSTRUCTED"


class PageType(StrEnum):
    NATIVE_TEXT = "NATIVE_TEXT"
    RASTER_SCAN = "RASTER_SCAN"
    MIXED = "MIXED"
    PHOTO = "PHOTO"
    EMPTY = "EMPTY"


class Glyph(BaseModel):
    """One user-visible character. ``synthetic`` marks spaces inferred from glyph gaps."""

    c: str
    quad: list[float]
    synthetic: bool = False


class TextStyle(BaseModel):
    font_name: str
    font_family: str
    font_key: str | None = None  # revision-scoped font resource key ("xref:<n>")
    embedded: bool = False
    subset: bool = False
    bold: bool = False
    italic: bool = False
    serif: bool = False
    mono: bool = False
    size_pt: float
    fill: str | None = "#000000"
    fill_components: list[float] = Field(default_factory=list)
    stroke: str | None = None
    render_mode: str = "fill"  # fill | stroke | fill_stroke | invisible
    opacity: float = 1.0
    letter_spacing_pt: float = 0.0
    horizontal_scale: float = 1.0
    rotation_deg: float = 0.0
    ascender: float = 0.9
    descender: float = -0.2
    space_width_pt: float | None = None
    text_align: str = "left"  # left | right | center (inferred hint, §17.3)


class SceneObject(BaseModel):
    id: str
    type: ObjectType
    source: ObjectSource
    bbox: list[float]
    quad: list[float] | None = None
    transform: list[float] | None = None
    z_index: int = 0
    confidence: float = 1.0
    style: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)
    native_ref: dict[str, Any] = Field(default_factory=dict)
    logical_group_id: str | None = None
    editable: bool = False


class PageScene(BaseModel):
    page_index: int
    width_pt: float
    height_pt: float
    rotation: int
    view_box: list[float]
    page_type: PageType
    analyzer_version: str = ANALYZER_VERSION
    objects: list[SceneObject] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def by_id(self, object_id: str) -> SceneObject | None:
        return next((item for item in self.objects if item.id == object_id), None)
