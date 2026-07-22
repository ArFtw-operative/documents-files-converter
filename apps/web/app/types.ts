export type User = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  quota_bytes: number;
};
export type VaultFile = {
  id: string;
  display_name: string;
  extension: string;
  mime_type: string;
  category: string;
  size: number;
  checksum_sha256: string;
  status: string;
  created_at: string;
  parent_file_id: string | null;
  folder_id: string | null;
  is_favorite: boolean;
  tags: Tag[];
  meta: Record<string, unknown>;
};
export type Job = {
  id: string;
  input_file_id: string;
  output_file_id: string | null;
  operation: string;
  target_format: string;
  status: string;
  progress: number;
  error_message: string | null;
  warning: string | null;
  created_at: string;
};
export type Capability = {
  operation: string;
  source_extensions: string[];
  target_extensions: string[];
  engine_id: string;
  approximate: boolean;
  limitations: string[];
  options: Record<string, unknown>;
};
export type Folder = { id: string; name: string; parent_id: string | null };
export type Tag = { id: string; name: string; color: string };
export type SavedPreset = {
  id: string;
  name: string;
  operation: string;
  target_format: string;
  options: Record<string, unknown>;
};
export type Engine = {
  engine_id: string;
  display_name: string;
  available: boolean;
  version: string;
};

export type PdfOperation = {
  kind: string;
  page?: number;
  pages?: number[];
  order?: number[];
  rect?: number[];
  points?: number[][];
  text?: string;
  replacement?: string;
  font?: string;
  font_size?: number;
  color?: string;
  fill?: string;
  width?: number;
  opacity?: number;
  rotation?: number;
  image_file_id?: string;
  uri?: string;
  field_name?: string;
  field_label?: string;
  field_value?: string;
  default_value?: string;
  required?: boolean;
  readonly?: boolean;
  hidden?: boolean;
  alignment?: string;
  format_type?: string;
  validation_pattern?: string;
  calculation?: string;
  choice_values?: string[];
  export_value?: string;
  max_length?: number;
  comb?: boolean;
  multiline?: boolean;
  password?: boolean;
  no_scroll?: boolean;
  tab_order?: number;
  search_terms?: string[];
  pattern_type?: string;
  custom_regex?: string;
  case_sensitive?: boolean;
  whole_word?: boolean;
  remove_metadata?: boolean;
  remove_comments?: boolean;
  remove_attachments?: boolean;
  remove_hidden_text?: boolean;
  remove_form_values?: boolean;
  attachment_name?: string;
  bookmark_title?: string;
  bookmark_level?: number;
  bookmark_index?: number;
  metadata?: Record<string, string>;
  object_id?: string;
  range_start?: number;
  range_end?: number;
  origin?: number[];
  font_resource?: string;
  font_xref?: number;
  reflow_policy?: string;
  font_policy?: string;
  source_xref?: number;
  source_digest?: string;
  source_rect?: number[];
  crop?: number[];
  vector_properties?: Record<string, unknown>;
  source_file_id?: string;
  source_page?: number;
  resize_mode?: string;
  page_width?: number;
  page_height?: number;
  page_boxes?: Record<string, number[]>;
  quads?: number[][];
  attachment_file_id?: string;
  annotation_name?: string;
  parent_annotation_name?: string;
  author?: string;
  subject?: string;
  annotation_status?: string;
  locked?: boolean;
  printable?: boolean;
  visible?: boolean;
  border_style?: string;
  line_start?: string;
  line_end?: string;
  stamp_type?: string;
  measurement_scale?: number;
  measurement_unit?: string;
  target_page?: number;
};

export type PdfRevision = {
  revision: number;
  operations: PdfOperation[];
  created_at: string;
};
export type PdfProject = {
  id: string;
  name: string;
  source_file_id: string;
  output_file_id: string | null;
  operations: PdfOperation[];
  revision: number;
  status: string;
  updated_at: string;
};
export type PdfDocumentInfo = {
  page_count: number;
  metadata: Record<string, string>;
  has_signatures: boolean;
  pages: Array<{
    page: number;
    width: number;
    height: number;
    rotation: number;
    fonts: string[];
    subset_fonts: string[];
    images: number;
    links: number;
    annotations: number;
    text_blocks: Array<{
      text: string;
      rect: number[];
      font: string;
      size: number;
      color: string;
    }>;
  }>;
};
export type PdfWorkspaceDocument = {
  id: string;
  source_file_id: string;
  name: string;
  status: string;
};
export type PdfWorkspaceSession = {
  id: string;
  document_id: string;
  base_version_id: string;
  status: string;
  revision: number;
  cursor: number;
  operations: PdfOperation[];
};
export type PdfSceneText = {
  id: string;
  type: "text_run";
  page: number;
  bounds: number[];
  transform: number[];
  editability: string;
  text: string;
  lock_state?: boolean;
  style: {
    font?: string;
    font_size?: number;
    color?: string;
    subset?: boolean;
    font_resource?: string;
    font_xref?: number;
  };
};
export type PdfSceneParagraph = {
  id: string;
  type: "text_block";
  page: number;
  bounds: number[];
  transform: number[];
  editability: string;
  text: string;
  line_count: number;
  lock_state?: boolean;
  style: PdfSceneText["style"];
};
export type PdfSceneImage = {
  id: string;
  type: "image";
  page: number;
  bounds: number[];
  editability: string;
  lock_state: boolean;
  source: { xref?: number };
  properties: { width?: number; height?: number };
};
export type PdfSceneVector = {
  id: string;
  type: "vector_path";
  page: number;
  bounds: number[];
  editability: string;
  lock_state: boolean;
  properties: {
    type?: string;
    width?: number;
    color?: number[];
    fill?: number[];
  };
};
export type PdfSceneFormField = {
  id: string;
  type: "form_field";
  page: number;
  bounds: number[];
  editability: string;
  lock_state: boolean;
  source: { xref?: number };
  properties: {
    name: string;
    label?: string;
    type?: string;
    value?: string | number | boolean | null;
    flags?: number;
    font?: string;
    font_size?: number;
    text_color?: number[];
    fill_color?: number[];
    border_color?: number[];
  };
};
export type PdfSceneLink = {
  id: string;
  type: "link";
  page: number;
  bounds: number[];
  editability: string;
  lock_state: boolean;
  source: { xref?: number };
  properties: { xref?: number; uri?: string; page?: number; kind?: number };
};
export type PdfSceneObject =
  | PdfSceneText
  | PdfSceneParagraph
  | PdfSceneImage
  | PdfSceneVector
  | PdfSceneFormField
  | PdfSceneLink
  | { type: string };

export type PdfAnnotation = {
  id: string;
  xref: number;
  page: number;
  type: string;
  rect: number[];
  author: string;
  subject: string;
  comment: string;
  created_at: string;
  modified_at: string;
  status: string;
  parent_id: string | null;
  thread_id: string;
  reply_count: number;
  locked: boolean;
  printable: boolean;
  visible: boolean;
  opacity: number;
  color: string;
  fill: string | null;
  width: number;
  border_style: string;
  attachment?: Record<string, unknown> | null;
};

export type PdfComparison = {
  before_file_id: string;
  after_file_id: string;
  before_name: string;
  after_name: string;
  summary: { total: number; by_type: Record<string, number> };
  differences: Array<{
    id: string;
    type: string;
    before_page: number | null;
    after_page: number | null;
    reviewed: boolean;
    details: Record<string, unknown>;
  }>;
};

export type Bookmark = { index: number; level: number; title: string; page: number };
export type EmbeddedAttachment = { name: string; size?: number; description?: string };

/** A live canvas selection: which scene object (or annotation) is active. */
export type Selection =
  | { kind: "text"; object: PdfSceneText }
  | { kind: "paragraph"; object: PdfSceneParagraph }
  | { kind: "image"; object: PdfSceneImage }
  | { kind: "vector"; object: PdfSceneVector }
  | { kind: "form_field"; object: PdfSceneFormField }
  | { kind: "link"; object: PdfSceneLink }
  | { kind: "annotation"; id: string }
  | null;
