/** TypeScript mirror of services/pdf_core/scene.py and the operation contract (§8, §23). */

export type ObjectType =
  | "TEXT_NATIVE" | "TEXT_OCR" | "TEXT_HANDWRITING" | "IMAGE" | "PATH" | "FORM_XOBJECT"
  | "INK_ANNOTATION" | "ANNOTATION_TEXT" | "ANNOTATION_HIGHLIGHT" | "TABLE" | "TABLE_CELL"
  | "BARCODE" | "SIGNATURE" | "STAMP" | "REDACTION" | "LINK" | "UNKNOWN";

export type ObjectSource =
  | "PDF_NATIVE" | "OCR_DERIVED" | "VISION_DERIVED" | "USER_CREATED" | "ANNOTATION_NATIVE"
  | "RASTER_RECONSTRUCTED";

export type PageType = "NATIVE_TEXT" | "RASTER_SCAN" | "MIXED" | "PHOTO" | "EMPTY";

export interface Glyph {
  c: string;
  quad: number[];
  synthetic: boolean;
}

export interface TextStyle {
  font_name: string;
  font_family: string;
  embedded: boolean;
  subset: boolean;
  bold: boolean;
  italic: boolean;
  serif: boolean;
  mono: boolean;
  size_pt: number;
  fill: string | null;
  stroke: string | null;
  render_mode: "fill" | "stroke" | "fill_stroke" | "invisible";
  opacity: number;
  letter_spacing_pt: number;
  horizontal_scale: number;
  rotation_deg: number;
  ascender: number;
  descender: number;
  space_width_pt: number | null;
  text_align: "left" | "right" | "center";
}

export interface SceneObject {
  id: string;
  type: ObjectType;
  source: ObjectSource;
  bbox: [number, number, number, number];
  quad: number[] | null;
  transform: number[] | null;
  z_index: number;
  confidence: number;
  style: Partial<TextStyle> & Record<string, unknown>;
  content: {
    text?: string;
    glyphs?: Glyph[];
    baseline_origin?: [number, number];
    advance_pt?: number;
    [key: string]: unknown;
  };
  native_ref?: Record<string, unknown>;
  logical_group_id: string | null;
  editable: boolean;
}

export interface PageScene {
  page_id: string;
  page_version: number;
  revision: number;
  page_index: number;
  width_pt: number;
  height_pt: number;
  rotation: number;
  view_box: [number, number, number, number];
  page_type: PageType;
  analyzer_version: string;
  objects: SceneObject[];
  warnings: string[];
}

export type OperationType =
  | "replace_text" | "add_text" | "delete_object" | "rotate_page" | "delete_page" | "reorder_page" | "insert_page";

export interface Operation {
  type: OperationType;
  page_id?: string | null;
  target_ids?: string[];
  payload?: Record<string, unknown>;
}

export interface OperationBatch {
  base_revision: number;
  client_batch_id: string;
  operations: Operation[];
}

export interface BatchResult {
  accepted: boolean;
  operation_batch_id: string;
  status: "pending" | "committed" | "failed";
  optimistic_revision: number;
  revision: number | null;
  warnings: string[];
  outcome: {
    outcomes?: Array<{
      page_id: string;
      object_id: string | null;
      kind: string;
      new_text: string | null;
      new_bbox: number[] | null;
      fit: Record<string, unknown>;
      warnings: string[];
      substitutions: Array<{ chars: string; original_font: string; used_font: string; reason: string }>;
    }>;
    elapsed_ms?: number;
  };
}

export interface PageInfo {
  index: number;
  page_id: string;
  version: number;
  width_pt: number | null;
  height_pt: number | null;
  rotation: number | null;
  page_type: PageType | null;
  analysis_status: string;
}

export interface DocumentDetail {
  id: string;
  name: string;
  status: "processing" | "ready" | "failed" | "deleted";
  error: string | null;
  page_count: number;
  current_revision: number;
  size: number;
  info: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  pages: PageInfo[];
  can_undo: boolean;
  can_redo: boolean;
}

export interface DocumentEvent {
  event: string;
  document_id: string;
  revision?: number;
  page_id?: string;
  version?: number;
  [key: string]: unknown;
}
