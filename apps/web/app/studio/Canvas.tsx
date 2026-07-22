"use client";
import { useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";
import { Loader2 } from "lucide-react";
import { SELECTION_META } from "./registry";
import type { StudioApi } from "./useStudio";
import type {
  PdfSceneImage,
  PdfSceneFormField,
  PdfSceneParagraph,
  PdfSceneLink,
  PdfSceneText,
  PdfSceneVector,
  Selection,
} from "../types";

const BASE_WIDTH = 820;

type OverlayKind = "text" | "paragraph" | "image" | "vector" | "form_field" | "link";

export function Canvas({ s }: { s: StudioApi }) {
  const scroller = useRef<HTMLDivElement>(null);
  const pageRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const dragState = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const [hovered, setHovered] = useState<string>("");
  const [panning, setPanning] = useState(false);
  const [renderedPageWidth, setRenderedPageWidth] = useState(0);
  const pageInfo = s.pageInfo;

  const placing = s.tool !== "select" && s.tool !== "edit_text" && s.tool !== "hand";
  const directTextEditing =
    s.workMode === "edit" && (s.tool === "select" || s.tool === "edit_text");
  const pageWidthPx = BASE_WIDTH * s.zoom;
  const pxPerPoint = pageInfo ? (renderedPageWidth || pageWidthPx) / pageInfo.width : 1;

  useEffect(() => {
    if (s.inlineEdit && editorRef.current) {
      editorRef.current.focus();
      const caret = s.inlineEdit.caret ?? s.inlineEdit.value.length;
      editorRef.current.setSelectionRange(caret, caret);
    }
  }, [s.inlineEdit?.object.id]);

  useEffect(() => {
    if (!s.fitRequest || !scroller.current) return;
    const available = Math.max(320, scroller.current.clientWidth - 64);
    s.setZoom(Math.max(0.4, Math.min(4, available / BASE_WIDTH)));
  }, [s.fitRequest]);

  useEffect(() => {
    if (!pageRef.current) return;
    const update = () => setRenderedPageWidth(pageRef.current?.getBoundingClientRect().width || 0);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(pageRef.current);
    return () => observer.disconnect();
  }, [s.page, pageWidthPx, pageInfo?.width]);

  if (!pageInfo)
    return (
      <div className="sd-canvas">
        <div className="sd-canvas-loading">
          <Loader2 className="sd-spin" /> Preparing the page…
        </div>
      </div>
    );

  const valid = (bounds?: number[] | null): bounds is number[] =>
    Array.isArray(bounds) && bounds.length >= 4 && bounds.every((n) => Number.isFinite(n));
  const box = (bounds: number[]) => ({
    left: `${(bounds[0] / pageInfo.width) * 100}%`,
    top: `${(bounds[1] / pageInfo.height) * 100}%`,
    width: `${((bounds[2] - bounds[0]) / pageInfo.width) * 100}%`,
    height: `${((bounds[3] - bounds[1]) / pageInfo.height) * 100}%`,
  });

  const selectedId =
    s.selection && s.selection.kind !== "annotation"
      ? s.selection.object.id
      : "";

  function overlay(
    kind: OverlayKind,
    object: PdfSceneText | PdfSceneParagraph | PdfSceneImage | PdfSceneVector | PdfSceneFormField | PdfSceneLink,
    onSelect: () => void,
    onEdit?: (event: MouseEvent<HTMLDivElement>) => void,
  ) {
    if (!valid(object.bounds)) return null;
    const meta =
      ["text", "paragraph"].includes(kind) && (object.editability === "Editable with reconstruction")
        ? { ...SELECTION_META.text, label: SELECTION_META.text.label }
        : SELECTION_META[kind];
    const reconstruction =
      object.editability === "Editable with reconstruction";
    const locked =
      (object as PdfSceneImage).lock_state || object.editability === "Protected";
    const active = selectedId === object.id;
    const show = active || hovered === object.id;
    return (
      <div
        key={object.id}
        className={`sd-obj sd-obj-${kind}${active ? " active" : ""}${reconstruction ? " reconstruction" : ""}${locked ? " locked" : ""}`}
        style={{ ...box(object.bounds), ["--sel" as string]: meta.color }}
        onMouseEnter={() => setHovered(object.id)}
        onMouseLeave={() => setHovered((h) => (h === object.id ? "" : h))}
        onClick={(event) => {
          if (placing) return;
          event.stopPropagation();
          onSelect();
          if (
            onEdit &&
            (s.tool === "edit_text" ||
              (s.workMode === "edit" && ["text", "paragraph"].includes(kind)))
          )
            onEdit(event);
        }}
        onDoubleClick={(event) => {
          if (!onEdit) return;
          event.stopPropagation();
          onEdit(event);
        }}
      >
        {show && (
          <span className="sd-obj-label" style={{ background: meta.color }}>
            {meta.label}
            {locked ? " · locked" : reconstruction ? " · reconstruct" : ""}
          </span>
        )}
      </div>
    );
  }

  const editing = s.inlineEdit;

  function caretFromClick(
    object: PdfSceneText | PdfSceneParagraph,
    event: MouseEvent<HTMLDivElement>,
  ) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const fontPixels = Math.max(8, (object.style.font_size ?? 12) * pxPerPoint);
    const lines = object.text.split("\n");
    const line = Math.max(
      0,
      Math.min(lines.length - 1, Math.floor((event.clientY - bounds.top) / (fontPixels * 1.05))),
    );
    const column = Math.max(
      0,
      Math.min(lines[line].length, Math.round((event.clientX - bounds.left) / (fontPixels * 0.52))),
    );
    return lines.slice(0, line).reduce((total, value) => total + value.length + 1, 0) + column;
  }

  return (
    <div
      className={`sd-canvas${placing ? " placing" : ""}${s.tool === "hand" ? " grab" : ""}${panning ? " grabbing" : ""}`}
      ref={scroller}
      onPointerDown={(event) => {
        if (s.tool !== "hand" || !scroller.current) return;
        dragState.current = {
          x: event.clientX,
          y: event.clientY,
          left: scroller.current.scrollLeft,
          top: scroller.current.scrollTop,
        };
        event.currentTarget.setPointerCapture(event.pointerId);
        setPanning(true);
      }}
      onPointerMove={(event) => {
        if (!dragState.current || !scroller.current) return;
        scroller.current.scrollLeft =
          dragState.current.left - (event.clientX - dragState.current.x);
        scroller.current.scrollTop =
          dragState.current.top - (event.clientY - dragState.current.y);
      }}
      onPointerUp={(event) => {
        if (!dragState.current) return;
        dragState.current = null;
        event.currentTarget.releasePointerCapture(event.pointerId);
        setPanning(false);
      }}
      onPointerCancel={() => {
        dragState.current = null;
        setPanning(false);
      }}
    >
      <div className="sd-canvas-stage">
        <div
          ref={pageRef}
          className="sd-page"
          style={{ width: pageWidthPx, aspectRatio: `${pageInfo.width}/${pageInfo.height}` }}
          onClick={(event) => {
            if (placing) {
              s.addOperation(event);
            } else {
              s.setSelection(null);
              s.setInlineEdit(null);
            }
          }}
        >
          {s.pageImage ? (
            <img src={s.pageImage} alt={`Page ${s.page}`} draggable={false} />
          ) : (
            <div className="sd-page-loading">
              <Loader2 className="sd-spin" />
            </div>
          )}

          {/* Native text runs */}
          {!placing && !directTextEditing &&
            s.sceneText.map((object) =>
              overlay(
                "text",
                object,
                () => s.selectObject({ kind: "text", object }),
                (event) => s.beginInlineEdit(object, caretFromClick(object, event)),
              ),
            )}
          {/* Multiline paragraph blocks are the editing targets for Edit Text. */}
          {directTextEditing &&
            s.sceneParagraphs.map((object) =>
              overlay(
                "paragraph",
                object,
                () => s.selectObject({ kind: "paragraph", object }),
                (event) => s.beginInlineEdit(object, caretFromClick(object, event)),
              ),
            )}
          {/* Images */}
          {!placing && !directTextEditing &&
            s.sceneImages.map((object) =>
              overlay("image", object, () =>
                s.selectObject({ kind: "image", object }),
              ),
            )}
          {/* Vector paths */}
          {!placing && !directTextEditing &&
            s.sceneVectors.map((object) =>
              overlay("vector", object, () =>
                s.selectObject({ kind: "vector", object }),
              ),
            )}
          {/* AcroForm fields */}
          {!placing && !directTextEditing &&
            s.sceneFields.map((object) =>
              overlay("form_field", object, () =>
                s.selectObject({ kind: "form_field", object }),
              ),
            )}
          {/* Existing hyperlinks */}
          {!placing && !directTextEditing &&
            s.sceneLinks.map((object) =>
              overlay("link", object, () =>
                s.selectObject({ kind: "link", object }),
              ),
            )}

          {/* Pending (unsaved) edits queued for this page */}
          {s.pageOps.map(({ operation, index }) => {
            const rect = operation.rect as number[];
            if (!valid(rect)) return null;
            const redact = operation.kind === "redact" || operation.kind.startsWith("redact");
            if (operation.kind === "content.add_text") {
              return (
                <div key={`op-${index}`} className="sd-pending-live" style={box(rect)}>
                  <textarea
                    aria-label="Live PDF text box"
                    autoFocus
                    value={String(operation.text || "")}
                    style={{
                      fontFamily: `"${String(operation.font || "Helvetica").replaceAll('"', '')}", sans-serif`,
                      fontSize: `${Math.max(8, Number(operation.font_size || 12) * pxPerPoint)}px`,
                      color: String(operation.color || "#000000"),
                      opacity: Number(operation.opacity ?? 1),
                    }}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => s.updatePendingOperation(index, { text: event.target.value })}
                  />
                  <button aria-label="Remove text box" onClick={(event) => { event.stopPropagation(); s.removePendingOperation(index); }}>×</button>
                </div>
              );
            }
            if (operation.kind === "content.add_shape") {
              const shape = String(operation.text || "rectangle");
              return (
                <div
                  key={`op-${index}`}
                  className={`sd-pending-shape ${shape}`}
                  style={{
                    ...box(rect),
                    borderColor: String(operation.color || "#000000"),
                    borderWidth: Number(operation.width || 1),
                    background: shape === "line" ? "transparent" : String(operation.fill || "transparent"),
                    opacity: Number(operation.opacity ?? 1),
                  }}
                >
                  <button aria-label="Remove shape" onClick={(event) => { event.stopPropagation(); s.removePendingOperation(index); }}>×</button>
                </div>
              );
            }
            return (
              <div
                key={`op-${operation.kind}-${index}`}
                className={`sd-pending${redact ? " redact" : ""}`}
                style={{
                  ...box(rect),
                  borderColor: operation.color,
                  background: redact
                    ? "#111"
                    : `${operation.fill || operation.color || "#2563eb"}22`,
                  opacity: operation.opacity ?? 1,
                }}
              >
                <button className="sd-pending-remove" aria-label={`Remove ${operation.kind}`} onClick={(event) => { event.stopPropagation(); s.removePendingOperation(index); }}>×</button>
                <span>
                  {operation.kind.includes("text")
                    ? operation.text
                    : operation.kind.split(".").pop()}
                </span>
              </div>
            );
          })}

          {/* Inline text editor */}
          {editing && valid(editing.object.bounds) && (
            <textarea
              ref={editorRef}
              className="sd-inline-editor"
              value={editing.value}
              style={{
                ...box(editing.object.bounds),
                fontSize: Math.max(
                  8,
                  (editing.object.style.font_size ?? 12) * pxPerPoint,
                ),
                fontFamily: editing.object.style.font
                  ? `"${editing.object.style.font.replaceAll('"', '')}", sans-serif`
                  : undefined,
                color: editing.object.style.color ?? "#111",
              }}
              onChange={(event) =>
                s.setInlineEdit({ object: editing.object, value: event.target.value, caret: editing.caret })
              }
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  s.setInlineEdit(null);
                }
                if (
                  event.key === "Enter" &&
                  (editing.object.type === "text_run" || event.ctrlKey || event.metaKey) &&
                  !event.shiftKey
                ) {
                  event.preventDefault();
                  void s.replaceTextObject(editing.object, editing.value);
                }
              }}
              onBlur={() => {
                if (editing.value !== editing.object.text)
                  void s.replaceTextObject(editing.object, editing.value);
                else s.setInlineEdit(null);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
