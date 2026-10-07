import type { SceneObject } from "@folio/scene-schema";
import { pdfRectToViewport, type Matrix } from "@folio/coordinate-engine";
import { Bold, Italic, PencilLine, Trash2 } from "lucide-react";

const LABELS: Record<string, string> = {
  IMAGE: "Image", PATH: "Shape", INK_ANNOTATION: "Ink", ANNOTATION_TEXT: "Note", ANNOTATION_HIGHLIGHT: "Highlight",
  LINK: "Link", TEXT_NATIVE: "Text",
};

/** Context toolbar near the selection (§4.7). Formatting reflects the source style; it is
 * preserved automatically on edit. */
export function FloatingToolbar({ obj, matrix, pageWidth, onEdit, onDelete }: {
  obj: SceneObject; matrix: Matrix; pageWidth: number; onEdit: () => void; onDelete: () => void;
}) {
  const [x0, y0, , y1] = pdfRectToViewport(matrix, obj.bbox);
  const above = y0 > 44;
  const left = Math.max(4, Math.min(x0, pageWidth - 320));
  const style = obj.style;
  const isText = obj.type === "TEXT_NATIVE";
  return (
    <div
      role="toolbar"
      aria-label="Selection"
      className="chrome border rounded-lg shadow-lg flex items-center gap-1 px-1.5 py-1 text-xs"
      style={{ position: "absolute", left, top: above ? y0 - 40 : y1 + 6, zIndex: 5 }}
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
    >
      {isText ? (
        <>
          <span className="px-1.5 max-w-36 truncate" title={String(style.font_name)}>{String(style.font_family || style.font_name)}</span>
          <span className="px-1 tabular-nums muted whitespace-nowrap">{Number(style.size_pt).toFixed(1).replace(/\.0$/, "")} pt</span>
          <span className="icon-btn !size-6" data-active={!!style.bold} aria-label="Bold"><Bold size={13} aria-hidden /></span>
          <span className="icon-btn !size-6" data-active={!!style.italic} aria-label="Italic"><Italic size={13} aria-hidden /></span>
          <span className="inline-block size-4 rounded border border-[var(--chrome-border)]" title={String(style.fill ?? style.stroke)}
            style={{ background: String(style.fill ?? style.stroke ?? "#000") }} />
          <span className="w-px h-5 bg-[var(--chrome-border)] mx-1" />
          {obj.editable && (
            <button className="btn !h-7 !px-2" onClick={onEdit}><PencilLine size={13} aria-hidden /> Edit</button>
          )}
          {obj.editable && (
            <button className="icon-btn !size-7" aria-label="Delete text" onClick={onDelete}><Trash2 size={14} aria-hidden /></button>
          )}
        </>
      ) : (
        <span className="px-2 py-1 muted">{LABELS[obj.type] ?? obj.type}</span>
      )}
    </div>
  );
}
