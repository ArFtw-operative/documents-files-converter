"use client";
import type { LucideIcon } from "lucide-react";
import {
  Crop,
  Eraser,
  Eye,
  GitCompare,
  Hand,
  Highlighter,
  Image as ImageIcon,
  Link2,
  MessageSquare,
  MousePointer2,
  Pencil,
  PenTool,
  RefreshCw,
  ScanLine,
  Shield,
  Square,
  Stamp,
  StickyNote,
  Strikethrough,
  Type,
  Underline,
} from "lucide-react";
import type { WorkMode } from "./useStudio";

export type ModeDef = {
  id: WorkMode;
  label: string;
  icon: LucideIcon;
  /** Honest availability note; when set the mode is partial/unavailable. */
  note?: string;
};

export const MODES: ModeDef[] = [
  { id: "view", label: "View", icon: Eye },
  { id: "edit", label: "Edit", icon: Pencil },
  { id: "comment", label: "Comment", icon: MessageSquare },
  { id: "organize", label: "Organize", icon: Square },
  { id: "forms", label: "Forms", icon: Type },
  { id: "sign", label: "Sign", icon: PenTool, note: "Visual signatures only — certificate/PKI signing isn't available in this build." },
  { id: "protect", label: "Protect", icon: Shield },
  { id: "redact", label: "Redact", icon: Eraser },
  { id: "compare", label: "Compare", icon: GitCompare },
  { id: "convert", label: "Convert", icon: RefreshCw },
  { id: "ocr", label: "OCR", icon: ScanLine },
];

/** Per-object-type selection styling and label (Spec §5). */
export const SELECTION_META: Record<
  string,
  { color: string; label: string; icon: LucideIcon }
> = {
  text: { color: "#2563eb", label: "Text Run", icon: Type },
  paragraph: { color: "#1d4ed8", label: "Paragraph", icon: Type },
  image: { color: "#7c3aed", label: "Image", icon: ImageIcon },
  vector: { color: "#0891b2", label: "Vector Path", icon: PenTool },
  form_field: { color: "#16a34a", label: "Form Field", icon: Type },
  link: { color: "#4f46e5", label: "Link", icon: Link2 },
  annotation: { color: "#ea580c", label: "Annotation", icon: MessageSquare },
  redaction: { color: "#dc2626", label: "Redaction", icon: Eraser },
  ocr: { color: "#6b7280", label: "OCR Text Region", icon: ScanLine },
};

export const TOOL_ICONS: Record<string, LucideIcon> = {
  select: MousePointer2,
  hand: Hand,
  edit_text: Type,
  text: Type,
  image: ImageIcon,
  shape: Square,
  draw: Pencil,
  link: Link2,
  crop: Crop,
  highlight: Highlighter,
  underline: Underline,
  strikeout: Strikethrough,
  comment: StickyNote,
  free_text: MessageSquare,
  stamp: Stamp,
  redact: Eraser,
  signature: PenTool,
  form: Type,
};
