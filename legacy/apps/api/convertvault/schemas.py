from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class SetupRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=4096)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    quota_bytes: int


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    color: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    owner_id: str
    parent_file_id: str | None
    folder_id: str | None
    original_name: str
    display_name: str
    extension: str
    mime_type: str
    category: str
    size: int
    checksum_sha256: str
    status: str
    is_favorite: bool
    meta: dict
    tags: list[TagOut] = Field(default_factory=list)
    created_at: datetime
    deleted_at: datetime | None


class JobCreate(BaseModel):
    input_file_id: str
    input_file_ids: list[str] = Field(default_factory=list, max_length=100)
    operation: str = "convert"
    target_format: str = Field(pattern=r"^[a-zA-Z0-9]+$")
    options: dict = Field(default_factory=dict)


class PdfEditOperation(BaseModel):
    kind: Literal[
        "page.reorder", "page.delete", "page.rotate", "page.crop", "page.insert_blank",
        "page.insert_from_pdf", "page.replace_from_pdf", "page.resize", "page.set_boxes",
        "content.add_text", "content.add_image", "content.add_shape", "content.draw",
        "content.replace_text", "content.edit_text_object",
        "content.transform_image", "content.replace_image_object", "content.delete_image_object",
        "content.transform_vector", "content.delete_vector_object",
        "redact", "redact.search", "annotate.highlight", "annotate.underline", "annotate.squiggly",
        "annotate.strikeout", "annotate.comment", "annotate.free_text", "annotate.callout",
        "annotate.ink", "annotate.line", "annotate.arrow", "annotate.rectangle", "annotate.ellipse",
        "annotate.polygon", "annotate.polyline", "annotate.stamp", "annotate.attachment",
        "annotate.caret", "annotate.replace_text", "annotate.redaction_mark", "annotate.measurement",
        "annotate.update", "annotate.reply", "annotate.delete", "link.add",
        "form.text", "form.multiline", "form.checkbox", "form.radio", "form.combo",
        "form.listbox", "form.pushbutton", "form.signature", "form.date", "form.numeric",
        "form.update", "form.delete", "form.reset", "form.flatten", "form.import_data",
        "attachment.add", "attachment.replace", "attachment.delete",
        "bookmark.add", "bookmark.update", "bookmark.delete",
        "signature.add", "watermark.text", "header_footer",
        "metadata.set",
    ]
    page: int | None = Field(default=None, ge=1)
    pages: list[int] = Field(default_factory=list, max_length=10000)
    order: list[int] = Field(default_factory=list, max_length=10000)
    rect: list[float] | None = Field(default=None, min_length=4, max_length=4)
    points: list[list[float]] = Field(default_factory=list, max_length=10000)
    quads: list[list[float]] = Field(default_factory=list, max_length=10000)
    text: str | None = Field(default=None, max_length=10000)
    replacement: str | None = Field(default=None, max_length=10000)
    font: str = Field(default="Helvetica", max_length=120)
    font_size: float = Field(default=12, ge=1, le=500)
    color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    fill: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    width: float = Field(default=1, ge=0.1, le=100)
    opacity: float = Field(default=1, ge=0, le=1)
    rotation: float = Field(default=0, ge=-360, le=360)
    image_file_id: str | None = None
    uri: str | None = Field(default=None, max_length=2048)
    target_page: int | None = Field(default=None, ge=1)
    field_name: str | None = Field(default=None, max_length=120)
    field_label: str | None = Field(default=None, max_length=255)
    field_value: str | None = Field(default=None, max_length=10000)
    default_value: str | None = Field(default=None, max_length=10000)
    required: bool = False
    readonly: bool = False
    hidden: bool = False
    alignment: Literal["left", "center", "right"] = "left"
    format_type: Literal["none", "date", "number", "special", "time"] = "none"
    validation_pattern: str | None = Field(default=None, max_length=500)
    calculation: str | None = Field(default=None, max_length=500)
    choice_values: list[str] = Field(default_factory=list, max_length=1000)
    export_value: str | None = Field(default=None, max_length=1000)
    max_length: int | None = Field(default=None, ge=0, le=100000)
    comb: bool = False
    multiline: bool = False
    password: bool = False
    no_scroll: bool = False
    tab_order: int | None = Field(default=None, ge=1, le=100000)
    search_terms: list[str] = Field(default_factory=list, max_length=10000)
    pattern_type: Literal["keyword", "name", "email", "phone", "account", "credit_card", "national_id", "ip", "date", "custom_regex"] | None = None
    custom_regex: str | None = Field(default=None, max_length=1000)
    case_sensitive: bool = False
    whole_word: bool = False
    remove_metadata: bool = False
    remove_comments: bool = False
    remove_attachments: bool = False
    remove_hidden_text: bool = True
    remove_form_values: bool = False
    attachment_name: str | None = Field(default=None, max_length=255)
    bookmark_title: str | None = Field(default=None, max_length=500)
    bookmark_level: int | None = Field(default=None, ge=1, le=32)
    bookmark_index: int | None = Field(default=None, ge=0, le=100000)
    metadata: dict[str, str] = Field(default_factory=dict)
    page_width: float | None = Field(default=None, ge=36, le=14400)
    page_height: float | None = Field(default=None, ge=36, le=14400)
    source_file_id: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    resize_mode: Literal["stretch", "fit", "fill"] = "fit"
    page_boxes: dict[str, list[float]] = Field(default_factory=dict)
    object_id: str | None = Field(default=None, max_length=128)
    range_start: int | None = Field(default=None, ge=0)
    range_end: int | None = Field(default=None, ge=0)
    origin: list[float] | None = Field(default=None, min_length=2, max_length=2)
    font_resource: str | None = Field(default=None, max_length=128)
    font_xref: int | None = Field(default=None, ge=0)
    reflow_policy: Literal["preserve_box", "preserve_line_positions", "expand_box", "reduce_font", "manual"] = "preserve_line_positions"
    font_policy: Literal["preserve_or_prompt", "substitute", "cancel"] = "preserve_or_prompt"
    source_xref: int | None = Field(default=None, ge=1)
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{16,128}$")
    source_rect: list[float] | None = Field(default=None, min_length=4, max_length=4)
    crop: list[float] | None = Field(default=None, min_length=4, max_length=4)
    vector_properties: dict = Field(default_factory=dict)
    attachment_file_id: str | None = None
    annotation_name: str | None = Field(default=None, max_length=128)
    parent_annotation_name: str | None = Field(default=None, max_length=128)
    author: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default=None, max_length=255)
    annotation_status: Literal["none", "accepted", "rejected", "cancelled", "completed", "open", "closed"] = "none"
    locked: bool = False
    printable: bool = True
    visible: bool = True
    border_style: Literal["solid", "dashed", "beveled", "inset", "underline"] = "solid"
    line_start: str | None = Field(default=None, max_length=40)
    line_end: str | None = Field(default=None, max_length=40)
    stamp_type: str | None = Field(default=None, max_length=60)
    measurement_scale: float | None = Field(default=None, gt=0, le=1000000)
    measurement_unit: str | None = Field(default=None, max_length=24)

    @model_validator(mode="after")
    def validate_for_kind(self):
        page_kinds = {"page.rotate", "page.crop", "page.replace_from_pdf", "page.resize", "page.set_boxes",
                      "content.add_text", "content.add_image",
                      "content.add_shape", "content.draw", "content.replace_text", "redact",
                      "content.edit_text_object", "content.transform_image", "content.replace_image_object",
                      "content.delete_image_object", "content.transform_vector", "content.delete_vector_object",
                      "annotate.highlight", "annotate.underline", "annotate.squiggly", "annotate.strikeout",
                      "annotate.comment", "annotate.free_text", "annotate.callout", "annotate.ink",
                      "annotate.line", "annotate.arrow", "annotate.rectangle", "annotate.ellipse",
                      "annotate.polygon", "annotate.polyline", "annotate.stamp", "annotate.attachment",
                      "annotate.caret", "annotate.replace_text", "annotate.redaction_mark",
                      "annotate.measurement", "annotate.update", "annotate.reply", "annotate.delete",
                      "link.add", "form.text", "form.multiline", "form.checkbox", "form.radio",
                      "form.combo", "form.listbox", "form.pushbutton", "form.signature",
                      "form.date", "form.numeric", "form.update", "form.delete",
                      "signature.add"}
        if self.kind in page_kinds and not self.page: raise ValueError("This operation requires a page number")
        rect_kinds = {"page.crop", "content.add_text", "content.add_image", "content.add_shape",
                      "content.edit_text_object", "redact", "annotate.highlight", "annotate.underline", "annotate.strikeout",
                      "annotate.squiggly", "annotate.comment", "annotate.free_text", "annotate.callout",
                      "annotate.rectangle", "annotate.ellipse", "annotate.stamp", "annotate.attachment",
                      "annotate.caret", "annotate.replace_text", "annotate.redaction_mark", "annotate.measurement",
                      "link.add", "form.text", "form.multiline", "form.checkbox", "form.radio",
                      "form.combo", "form.listbox", "form.pushbutton", "form.signature",
                      "form.date", "form.numeric", "signature.add"}
        if self.kind in rect_kinds and not self.rect: raise ValueError("This operation requires a rectangle")
        if self.rect and (self.rect[2] <= self.rect[0] or self.rect[3] <= self.rect[1]):
            raise ValueError("Rectangle coordinates must have positive width and height")
        if self.kind == "page.reorder" and not self.order: raise ValueError("Page order cannot be empty")
        if self.kind == "page.delete" and not self.pages: raise ValueError("Select pages to delete")
        if self.kind in {"page.insert_from_pdf", "page.replace_from_pdf"}:
            if not self.source_file_id or not self.source_page:
                raise ValueError("Importing a page requires a source PDF file and source page number")
            if self.kind == "page.insert_from_pdf" and not self.page:
                raise ValueError("Imported page insertion requires a destination position")
        if self.kind == "page.resize" and (not self.page_width or not self.page_height):
            raise ValueError("Page resize requires target width and height")
        if self.kind == "page.set_boxes":
            allowed_boxes = {"media", "crop", "bleed", "trim", "art"}
            if not self.page_boxes or not set(self.page_boxes) <= allowed_boxes:
                raise ValueError("Page boxes must contain media, crop, bleed, trim, or art rectangles")
            if any(len(value) != 4 or value[2] <= value[0] or value[3] <= value[1]
                   for value in self.page_boxes.values()):
                raise ValueError("Every page box must have four coordinates and positive size")
        if self.kind in {"content.add_text", "annotate.comment", "annotate.free_text", "watermark.text", "header_footer"} and not self.text:
            raise ValueError("This operation requires text")
        if self.kind in {"content.add_image", "signature.add"} and not self.image_file_id:
            raise ValueError("This operation requires an image file")
        if self.kind.startswith("form.") and self.kind not in {"form.flatten", "form.import_data", "form.reset"} and not self.field_name:
            raise ValueError("Form field operations require a field name")
        if self.kind in {"form.combo", "form.listbox", "form.radio"} and not self.choice_values:
            raise ValueError("Choice and radio fields require at least one choice value")
        if self.comb and (not self.max_length or self.multiline or self.password):
            raise ValueError("Comb fields require a maximum length and cannot be multiline or password fields")
        if self.validation_pattern:
            try:
                re.compile(self.validation_pattern)
            except re.error as exc:
                raise ValueError("Form validation pattern is not a valid regular expression") from exc
        if self.kind == "content.draw" and len(self.points) < 2: raise ValueError("Drawing requires at least two points")
        if self.kind in {"annotate.ink", "annotate.polygon", "annotate.polyline"} and len(self.points) < 2:
            raise ValueError("This annotation requires at least two points")
        if self.kind in {"annotate.line", "annotate.arrow", "annotate.measurement"} and not self.rect and len(self.points) < 2:
            raise ValueError("This annotation requires a line start and end")
        if self.kind == "annotate.attachment" and not self.attachment_file_id:
            raise ValueError("An attachment annotation requires a file")
        if self.kind in {"annotate.update", "annotate.delete"} and not self.annotation_name:
            raise ValueError("Annotation updates require a stable annotation name")
        if self.kind == "annotate.reply" and (not self.annotation_name or not self.parent_annotation_name or self.text is None):
            raise ValueError("Annotation replies require a parent, stable reply name, and comment")
        if self.kind == "content.replace_text" and (not self.text or self.replacement is None):
            raise ValueError("Text replacement requires search and replacement text")
        if self.kind == "redact.search":
            if not self.search_terms and not self.pattern_type:
                raise ValueError("Search redaction requires keywords or a pattern type")
            if self.pattern_type == "custom_regex" and not self.custom_regex:
                raise ValueError("Custom-pattern redaction requires a regular expression")
            if self.custom_regex:
                try:
                    re.compile(self.custom_regex)
                except re.error as exc:
                    raise ValueError("Redaction regular expression is invalid") from exc
        if self.kind in {"attachment.add", "attachment.replace"} and not self.attachment_file_id:
            raise ValueError("Adding or replacing an embedded attachment requires a vault file")
        if self.kind in {"attachment.replace", "attachment.delete"} and not self.attachment_name:
            raise ValueError("Replacing or deleting an embedded attachment requires its name")
        if self.kind in {"bookmark.add", "bookmark.update"} and (not self.bookmark_title or not self.target_page):
            raise ValueError("Bookmark creation and updates require a title and destination page")
        if self.kind in {"bookmark.update", "bookmark.delete"} and self.bookmark_index is None:
            raise ValueError("Bookmark updates and deletion require a bookmark index")
        if self.kind == "content.edit_text_object":
            if not self.object_id or self.text is None or self.replacement is None or not self.origin:
                raise ValueError("Native text editing requires a scene object, source text, replacement text, and baseline")
            if self.range_start is None or self.range_end is None or self.range_end < self.range_start:
                raise ValueError("Native text editing requires a valid character range")
        if self.kind in {"content.transform_image", "content.replace_image_object", "content.delete_image_object"}:
            if not self.object_id or (not self.source_xref and not self.source_digest) or not self.source_rect:
                raise ValueError("Existing-image editing requires a scene object, image resource, and source bounds")
            if self.kind == "content.replace_image_object" and not self.image_file_id:
                raise ValueError("Replacing an existing image requires a replacement image file")
            if self.crop and not (0 <= self.crop[0] < self.crop[2] <= 1 and 0 <= self.crop[1] < self.crop[3] <= 1):
                raise ValueError("Image crop values must be normalized left, top, right, bottom coordinates")
        if self.kind in {"content.transform_vector", "content.delete_vector_object"}:
            if not self.object_id or not self.source_rect or not self.vector_properties:
                raise ValueError("Existing-vector editing requires a scene object, source bounds, and path data")
        return self


class PdfProjectCreate(BaseModel):
    file_id: str
    name: str | None = Field(default=None, max_length=255)


class PdfProjectUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    operations: list[PdfEditOperation] = Field(max_length=5000)


class PdfDocumentCreate(BaseModel):
    file_id: str
    name: str | None = Field(default=None, min_length=1, max_length=255)


class PdfSessionCreate(BaseModel):
    base_version_id: str | None = None


class PdfCommandCreate(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    operation: PdfEditOperation
    object_id: str | None = Field(default=None, max_length=128)


class PdfHistoryAction(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")


class PdfTextRange(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Text range end must not be before its start")
        return self


class PdfImageObjectEditRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    action: Literal["transform", "replace", "delete"] = "transform"
    rect: list[float] | None = Field(default=None, min_length=4, max_length=4)
    rotation: float = Field(default=0, ge=-360, le=360)
    crop: list[float] | None = Field(default=None, min_length=4, max_length=4)
    image_file_id: str | None = None

    @model_validator(mode="after")
    def validate_image_edit(self):
        if self.action != "delete" and not self.rect:
            raise ValueError("Image transform and replacement require destination bounds")
        if self.rect and (self.rect[2] <= self.rect[0] or self.rect[3] <= self.rect[1]):
            raise ValueError("Image destination bounds must have positive width and height")
        if self.action == "replace" and not self.image_file_id:
            raise ValueError("Image replacement requires a replacement file")
        if self.crop and not (0 <= self.crop[0] < self.crop[2] <= 1 and 0 <= self.crop[1] < self.crop[3] <= 1):
            raise ValueError("Image crop values must be normalized left, top, right, bottom coordinates")
        return self


class PdfVectorObjectEditRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    action: Literal["transform", "delete"] = "transform"
    rect: list[float] | None = Field(default=None, min_length=4, max_length=4)
    rotation: float = Field(default=0, ge=-360, le=360)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    fill: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    width: float | None = Field(default=None, ge=0.1, le=100)
    opacity: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_vector_edit(self):
        if self.action != "delete" and not self.rect:
            raise ValueError("Vector transform requires destination bounds")
        if self.rect and (self.rect[2] <= self.rect[0] or self.rect[3] <= self.rect[1]):
            raise ValueError("Vector destination bounds must have positive width and height")
        return self


class PdfPageImportRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    action: Literal["insert", "replace"]
    page: int = Field(ge=1)
    source_file_id: str
    source_page: int = Field(ge=1)


class PdfPageGeometryRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    action: Literal["resize", "set_boxes"]
    width: float | None = Field(default=None, ge=36, le=14400)
    height: float | None = Field(default=None, ge=36, le=14400)
    resize_mode: Literal["stretch", "fit", "fill"] = "fit"
    boxes: dict[str, list[float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_geometry(self):
        if self.action == "resize" and (not self.width or not self.height):
            raise ValueError("Page resize requires width and height")
        if self.action == "set_boxes" and not self.boxes:
            raise ValueError("Page box editing requires at least one box")
        return self


class PdfAnnotationUpdateRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    text: str | None = Field(default=None, max_length=10000)
    author: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default=None, max_length=255)
    annotation_status: Literal["none", "accepted", "rejected", "cancelled", "completed", "open", "closed"] | None = None
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    fill: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    width: float | None = Field(default=None, ge=0.1, le=100)
    opacity: float | None = Field(default=None, ge=0, le=1)
    border_style: Literal["solid", "dashed", "beveled", "inset", "underline"] | None = None
    locked: bool | None = None
    printable: bool | None = None
    visible: bool | None = None


class PdfAnnotationReplyRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    text: str = Field(min_length=1, max_length=10000)
    author: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default="Reply", max_length=255)


class PdfFormDataImportRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    values: dict[str, str] = Field(max_length=10000)


class PdfCompareRequest(BaseModel):
    before_file_id: str
    after_file_id: str
    ignore_headers_footers: bool = False
    ignore_formatting: bool = False
    ignore_whitespace: bool = True

class PdfNativeTextEditRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    operation: Literal["replace_range"] = "replace_range"
    range: PdfTextRange
    text: str = Field(max_length=10000)
    reflow_policy: Literal["preserve_box", "preserve_line_positions", "expand_box", "reduce_font", "manual"] = "preserve_line_positions"
    font_policy: Literal["preserve_or_prompt", "substitute", "cancel"] = "preserve_or_prompt"
    replacement_font: str | None = Field(default=None, max_length=120)


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: str | None = None


class FileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=512)
    folder_id: str | None = None
    is_favorite: bool | None = None


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#176b4d", pattern=r"^#[0-9a-fA-F]{6}$")


class ShareCreate(BaseModel):
    expires_in_hours: int = Field(default=24, ge=1, le=24 * 30)
    download_limit: int | None = Field(default=None, ge=1, le=10000)


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    operation: str
    target_format: str = Field(pattern=r"^[a-zA-Z0-9]+$")
    options: dict = Field(default_factory=dict)


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(pattern="^(admin|user)$")


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None
    quota_bytes: int | None = Field(default=None, ge=1024 * 1024, le=10 * 1024**4)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    input_file_id: str
    output_file_id: str | None
    operation: str
    engine_id: str | None
    target_format: str
    options: dict
    status: str
    progress: int
    error_code: str | None
    error_message: str | None
    warning: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
