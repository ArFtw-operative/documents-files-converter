"use client";
import type { LucideIcon } from "lucide-react";
import {
  AlignLeft,
  CalendarDays,
  CheckSquare,
  ChevronDown,
  Circle,
  FileText,
  Hash,
  Highlighter,
  Image as ImageIcon,
  Link2,
  List,
  MessageSquare,
  MousePointer2,
  Paperclip,
  Pencil,
  PenTool,
  Square,
  Stamp,
  Strikethrough,
  StickyNote,
  Type,
  Underline,
} from "lucide-react";
import { MODES } from "./registry";
import type { StudioApi } from "./useStudio";

function ToolButton({
  icon: Icon,
  label,
  active,
  disabled,
  title,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  active?: boolean;
  disabled?: boolean;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`sd-tool${active ? " active" : ""}`}
      title={title ?? label}
      disabled={disabled}
      onClick={onClick}
    >
      <Icon />
      <span>{label}</span>
    </button>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="sd-tool-group">
      <div className="sd-tools-row">{children}</div>
      <span className="sd-group-label">{label}</span>
    </div>
  );
}

export function Ribbon({ s }: { s: StudioApi }) {
  const isTool = (id: string) => s.tool === id;
  const select = () => s.setTool("select");
  const annotation = (kind: string) => {
    s.setAnnotationKind(kind);
    s.setTool("annotation");
  };
  const field = (kind: string) => {
    s.setFormKind(kind);
    s.setTool("form");
  };

  return (
    <div className="sd-ribbon">
      <div className="sd-modes" role="tablist" aria-label="Work modes">
        {MODES.filter((mode) => mode.id !== "ocr" || s.hasCapability("pdf.ocr")).map((mode) => {
          const Icon = mode.icon;
          return (
            <button
              key={mode.id}
              type="button"
              role="tab"
              aria-selected={s.workMode === mode.id}
              className={`sd-mode${s.workMode === mode.id ? " active" : ""}`}
              title={mode.note ?? mode.label}
              onClick={() => {
                s.setWorkMode(mode.id);
                s.setTool("select");
                s.setSelection(null);
              }}
            >
              <Icon />
              <span>{mode.label}</span>
              {mode.note && <em className="sd-mode-dot" title={mode.note} />}
            </button>
          );
        })}
      </div>

      <div className="sd-toolstrip">
        {s.workMode === "view" && (
          <Group label="Navigate">
            <ToolButton icon={MousePointer2} label="Select" active={isTool("select")} onClick={select} />
            <ToolButton icon={Pencil} label="Hand" active={isTool("hand")} title="Pan the page" onClick={() => s.setTool("hand")} />
          </Group>
        )}

        {s.workMode === "edit" && (
          <>
            <Group label="Content">
              <ToolButton icon={MousePointer2} label="Select" active={isTool("select")} onClick={select} />
              <ToolButton icon={Type} label="Edit Text" title="Double-click any text to edit it in place" active={isTool("edit_text")} onClick={() => s.setTool("edit_text")} />
              <ToolButton icon={Type} label="Add Text" active={isTool("text")} onClick={() => s.setTool("text")} />
              <ToolButton icon={ImageIcon} label="Add Image" active={isTool("image")} onClick={() => s.setTool("image")} />
              <ToolButton icon={Square} label="Shape" active={isTool("shape")} onClick={() => s.setTool("shape")} />
              <ToolButton icon={Pencil} label="Draw" active={isTool("draw")} onClick={() => s.setTool("draw")} />
              <ToolButton icon={Link2} label="Link" active={isTool("link")} onClick={() => s.setTool("link")} />
              <ToolButton icon={Square} label="Crop" active={isTool("crop")} onClick={() => s.setTool("crop")} />
            </Group>
            <Group label="Document">
              <ToolButton icon={AlignLeft} label="Header/Footer" active={isTool("header_footer")} onClick={() => s.setTool("header_footer")} />
              <ToolButton icon={FileText} label="Watermark" active={isTool("watermark")} onClick={() => s.setTool("watermark")} />
              <ToolButton icon={FileText} label="Metadata" active={isTool("metadata")} onClick={() => s.setTool("metadata")} />
            </Group>
          </>
        )}

        {s.workMode === "comment" && (
          <>
            <Group label="Markup">
              <ToolButton icon={MousePointer2} label="Select" active={isTool("select")} onClick={select} />
              <ToolButton icon={Highlighter} label="Highlight" active={isTool("highlight")} onClick={() => s.setTool("highlight")} />
              <ToolButton icon={Underline} label="Underline" active={isTool("underline")} onClick={() => s.setTool("underline")} />
              <ToolButton icon={Strikethrough} label="Strikeout" active={isTool("strikeout")} onClick={() => s.setTool("strikeout")} />
            </Group>
            <Group label="Notes">
              <ToolButton icon={StickyNote} label="Sticky Note" active={isTool("comment")} onClick={() => s.setTool("comment")} />
              <ToolButton icon={MessageSquare} label="Text Box" active={isTool("free_text")} onClick={() => s.setTool("free_text")} />
              <ToolButton icon={Pencil} label="Draw" active={isTool("draw")} onClick={() => s.setTool("draw")} />
            </Group>
            <Group label="Insert">
              <ToolButton icon={Square} label="Shapes" active={isTool("annotation") && s.annotationKind === "annotate.rectangle"} onClick={() => annotation("annotate.rectangle")} />
              <ToolButton icon={Stamp} label="Stamp" active={isTool("annotation") && s.annotationKind === "annotate.stamp"} onClick={() => annotation("annotate.stamp")} />
              <ToolButton icon={Paperclip} label="Attach File" active={isTool("annotation") && s.annotationKind === "annotate.attachment"} onClick={() => annotation("annotate.attachment")} />
            </Group>
          </>
        )}

        {s.workMode === "organize" && (
          <Group label="Pages">
            <span className="sd-toolstrip-hint">
              Drag page tiles to reorder. Select a tile for rotate, duplicate, delete, extract, and insert actions.
            </span>
          </Group>
        )}

        {s.workMode === "forms" && (
          <>
            <Group label="Select">
              <ToolButton icon={MousePointer2} label="Select" active={isTool("select")} onClick={select} />
            </Group>
            <Group label="Fields">
              <ToolButton icon={Type} label="Text" active={isTool("form") && s.formKind === "form.text"} onClick={() => field("form.text")} />
              <ToolButton icon={AlignLeft} label="Multiline" active={isTool("form") && s.formKind === "form.multiline"} onClick={() => field("form.multiline")} />
              <ToolButton icon={CheckSquare} label="Checkbox" active={isTool("form") && s.formKind === "form.checkbox"} onClick={() => field("form.checkbox")} />
              <ToolButton icon={Circle} label="Radio" active={isTool("form") && s.formKind === "form.radio"} onClick={() => field("form.radio")} />
              <ToolButton icon={ChevronDown} label="Dropdown" active={isTool("form") && s.formKind === "form.combo"} onClick={() => field("form.combo")} />
              <ToolButton icon={List} label="List" active={isTool("form") && s.formKind === "form.listbox"} onClick={() => field("form.listbox")} />
              <ToolButton icon={CalendarDays} label="Date" active={isTool("form") && s.formKind === "form.date"} onClick={() => field("form.date")} />
              <ToolButton icon={Hash} label="Numeric" active={isTool("form") && s.formKind === "form.numeric"} onClick={() => field("form.numeric")} />
              <ToolButton icon={PenTool} label="Signature" active={isTool("form") && s.formKind === "form.signature"} onClick={() => field("form.signature")} />
            </Group>
          </>
        )}

        {s.workMode === "sign" && (
          <Group label="Signature">
            <ToolButton icon={MousePointer2} label="Select" active={isTool("select")} onClick={select} />
            <ToolButton icon={PenTool} label="Place Signature" active={isTool("signature")} onClick={() => s.setTool("signature")} />
          </Group>
        )}

        {s.workMode === "redact" && (
          <Group label="Redaction">
            <ToolButton icon={MousePointer2} label="Select" active={isTool("select")} onClick={select} />
            <ToolButton icon={Square} label="Mark Area" title="Draw a redaction box on the page" active={isTool("redact")} onClick={() => s.setTool("redact")} />
            <span className="sd-toolstrip-hint">
              Find-and-redact patterns and sanitisation are in the panel on the right.
            </span>
          </Group>
        )}

        {s.workMode === "compare" && (
          <Group label="Compare">
            <span className="sd-toolstrip-hint">
              Pick a second PDF in the right panel to run a text, object, page, and visual comparison.
            </span>
          </Group>
        )}

        {s.workMode === "protect" && (
          <Group label="Protect">
            <span className="sd-toolstrip-hint">
              Encryption, metadata removal, flattening, sanitising, and repair are in the right panel.
            </span>
          </Group>
        )}

        {s.workMode === "convert" && (
          <Group label="Convert">
            <span className="sd-toolstrip-hint">
              Merge, split, extract, compress, and render tools are in the right panel.
            </span>
          </Group>
        )}

        {s.workMode === "ocr" && (
          <Group label="OCR">
            <span className="sd-toolstrip-hint">
              Choose language and cleanup options in the right panel to make scans searchable.
            </span>
          </Group>
        )}

        <div className="sd-toolstrip-end">
          <label className="sd-lock" title="Keep the current tool active after each use">
            <input
              type="checkbox"
              checked={s.toolLock}
              onChange={(event) => s.setToolLock(event.target.checked)}
            />
            Keep tool active
          </label>
        </div>
      </div>
    </div>
  );
}
