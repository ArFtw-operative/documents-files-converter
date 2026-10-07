import { memo, useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import type { PageInfo, PageScene, SceneObject } from "@folio/scene-schema";
import {
  caretIndex,
  cssMatrix,
  pdfRectToViewport,
  quadToViewport,
  textFrameToViewport,
  viewportPointToPdf,
  type Matrix,
  type Point,
} from "@folio/coordinate-engine";
import { useScene } from "../../api/queries";
import { previewFontFamily } from "../pdf";
import { pageIndex } from "../spatial";
import { usePanels, useJobs, useSelection, useTool } from "../stores";
import type { useEditActions } from "../useEditActions";
import { InlineTextEditor, Mask, TextPreview, textStyle } from "../overlays/InlineTextEditor";
import { fitRatio, sampleBackground, textFrame } from "../overlays/textLayout";
import { FloatingToolbar } from "../overlays/FloatingToolbar";
import { ConfirmBubble } from "../overlays/ConfirmBubble";

type Actions = ReturnType<typeof useEditActions>;

interface Props {
  documentId: string;
  info: PageInfo;
  pdf: PDFDocumentProxy;
  revision: number;
  scale: number;
  width: number;
  height: number;
  actions: Actions;
}

function polygon(points: Point[]): string {
  return points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function outline(matrix: Matrix, obj: SceneObject): Point[] {
  if (obj.quad) return quadToViewport(matrix, obj.quad);
  const [x0, y0, x1, y1] = pdfRectToViewport(matrix, obj.bbox);
  return [[x0, y1], [x1, y1], [x1, y0], [x0, y0]];
}

export const PageView = memo(function PageView({ documentId, info, pdf, revision, scale, width, height, actions }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pdfPage, setPdfPage] = useState<PDFPageProxy | null>(null);
  const [matrix, setMatrix] = useState<Matrix | null>(null);
  const developer = usePanels((s) => s.developer);
  const scene = useScene(documentId, info.page_id, info.version, true).data;
  const tool = useTool((s) => s.tool);
  const hover = useSelection((s) => (s.hover?.pageId === info.page_id ? s.hover.objectId : null));
  const selected = useSelection((s) => (s.selection?.pageId === info.page_id ? s.selection.objectId : null));
  const editing = useSelection((s) => (s.editing?.pageId === info.page_id ? s.editing : null));
  const draft = useSelection((s) => (s.draft?.pageId === info.page_id ? s.draft : null));
  const pendingAll = useJobs((s) => s.pending);
  const pending = useMemo(() => Object.values(pendingAll).filter((p) => p.pageId === info.page_id), [pendingAll, info.page_id]);

  useEffect(() => {
    let alive = true;
    pdf.getPage(info.index + 1).then((page) => alive && setPdfPage(page)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [pdf, info.index]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!pdfPage || !canvas) return;
    const viewport = pdfPage.getViewport({ scale });
    const ratio = Math.min(window.devicePixelRatio || 1, 3);
    canvas.width = Math.floor(viewport.width * ratio);
    canvas.height = Math.floor(viewport.height * ratio);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    const task = pdfPage.render({ canvas, viewport, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined });
    task.promise
      .then(() => {
        setMatrix(viewport.transform as unknown as Matrix);
        useJobs.getState().settlePending(info.page_id, revision);
      })
      .catch(() => undefined);
    // Warm the font lookup used by the inline editor.
    pdfPage.getTextContent().catch(() => undefined);
    return () => task.cancel();
  }, [pdfPage, scale, revision, info.page_id]);

  const objectById = useMemo(() => new Map(scene?.objects.map((o) => [o.id, o]) ?? []), [scene]);

  const toPdf = useCallback(
    (event: ReactPointerEvent | React.MouseEvent): Point | null => {
      if (!matrix) return null;
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      return viewportPointToPdf(matrix, [event.clientX - rect.left, event.clientY - rect.top]);
    },
    [matrix],
  );

  const candidates = useCallback(
    (point: Point) => (scene ? pageIndex(scene).candidates(point, tool, 3 / scale) : []),
    [scene, tool, scale],
  );

  const frame = useRef(0);
  function onPointerMove(event: ReactPointerEvent) {
    if (tool === "pan") return;
    const point = toPdf(event);
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      const top = point ? candidates(point)[0] : undefined;
      const current = useSelection.getState().hover;
      if ((top?.id ?? null) !== (current?.pageId === info.page_id ? current.objectId : null)) {
        useSelection.getState().setHover(top ? { pageId: info.page_id, objectId: top.id } : null);
      }
    });
  }

  function startEditing(obj: SceneObject, point: Point) {
    const glyphs = obj.content.glyphs ?? [];
    const origin = obj.content.baseline_origin ?? [obj.bbox[0], obj.bbox[1]];
    const caret = caretIndex(point, origin, Number(obj.style.rotation_deg ?? 0), glyphs.map((g) => g.quad));
    useSelection.getState().startEditing({ pageId: info.page_id, objectId: obj.id }, caret);
  }

  function onClick(event: React.MouseEvent) {
    if (tool === "pan" || useSelection.getState().editing) return;
    const point = toPdf(event);
    if (!point) return;
    if (tool === "addText") {
      useSelection.getState().setDraft({ pageId: info.page_id, point: [point[0], point[1]] });
      return;
    }
    const list = candidates(point);
    let target = list[0];
    if (event.altKey && list.length > 1) {
      // Alt+click cycles through overlapping objects (§3.1).
      const key = list.map((o) => o.id).join("|");
      const cycle = useSelection.getState().cycle;
      const index = cycle?.key === key ? (cycle.index + 1) % list.length : 1;
      useSelection.getState().setCycle({ key, index });
      target = list[index];
    }
    if (!target) {
      useSelection.getState().select(null);
      return;
    }
    if (tool === "edit" && target.editable && !event.altKey && !pendingAll[target.id]) startEditing(target, point);
    else useSelection.getState().select({ pageId: info.page_id, objectId: target.id });
  }

  function onDoubleClick(event: React.MouseEvent) {
    const point = toPdf(event);
    if (!point || tool === "pan") return;
    const target = candidates(point)[0];
    if (target?.editable && !pendingAll[target.id]) startEditing(target, point);
  }

  const hoverObj = hover && hover !== selected && !editing ? objectById.get(hover) : undefined;
  const selectedObj = selected ? objectById.get(selected) : undefined;
  const cursor = tool === "pan" ? "grab" : tool === "addText" ? "crosshair" : hoverObj?.editable ? "text" : "default";

  return (
    <div
      className="page-shadow relative bg-white select-none"
      style={{ width, height, cursor }}
      onPointerMove={onPointerMove}
      onPointerLeave={() => useSelection.getState().hover?.pageId === info.page_id && useSelection.getState().setHover(null)}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      data-page-index={info.index}
    >
      <canvas ref={canvasRef} className="absolute inset-0" aria-label={`Page ${info.index + 1}`} />
      {matrix && scene && (
        <svg className="absolute inset-0 pointer-events-none" width={width} height={height} aria-hidden>
          {hoverObj && <polygon points={polygon(outline(matrix, hoverObj))} fill="none" stroke="rgb(37 99 235 / 0.55)" strokeWidth={1} />}
          {selectedObj && !editing && (
            <polygon points={polygon(outline(matrix, selectedObj))} fill="rgb(37 99 235 / 0.06)" stroke="#2563eb" strokeWidth={1.25} />
          )}
          {developer && scene.objects.filter((o) => o.type === "TEXT_NATIVE").map((o) => (
            <polygon key={o.id} points={polygon(outline(matrix, o))} fill="none" stroke="rgb(234 88 12 / 0.35)" strokeWidth={0.5} />
          ))}
        </svg>
      )}
      {matrix && pending.map((p) => {
        const obj = objectById.get(p.objectId);
        if (!obj || (editing && editing.objectId === p.objectId)) return null;
        const f = textFrame(matrix, obj);
        return <TextPreview key={p.objectId} frame={f} text={p.text} family={p.family ?? "sans-serif"}
          ratio={p.ratio ?? 1} background={p.background ?? "#fff"} />;
      })}
      {matrix && pdfPage && editing && objectById.get(editing.objectId) && (
        <EditorHost key={editing.objectId} page={pdfPage} scene={scene!} obj={objectById.get(editing.objectId)!}
          caret={editing.caret} matrix={matrix} canvas={canvasRef.current} pageId={info.page_id} actions={actions} />
      )}
      {matrix && draft && scene && (
        <DraftEditor scene={scene} point={draft.point} matrix={matrix} pageId={info.page_id} actions={actions} />
      )}
      {matrix && selectedObj && !editing && (
        <FloatingToolbar obj={selectedObj} matrix={matrix} pageWidth={width}
          onEdit={() => selectedObj.editable && startEditing(selectedObj, selectedObj.content.baseline_origin ?? [selectedObj.bbox[2], selectedObj.bbox[1]])}
          onDelete={() => selectedObj.editable && actions.deleteObject(info.page_id, selectedObj)} />
      )}
    </div>
  );
});

interface HostProps {
  page: PDFPageProxy;
  scene: PageScene;
  obj: SceneObject;
  caret: number;
  matrix: Matrix;
  canvas: HTMLCanvasElement | null;
  pageId: string;
  actions: Actions;
}

/** Resolves the preview font, then mounts the inline editor and handles commit outcomes. */
function EditorHost({ page, scene, obj, caret, matrix, canvas, pageId, actions }: HostProps) {
  const [family, setFamily] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [prompt, setPrompt] = useState<null | { kind: "fit"; text: string; required: number; available: number }
    | { kind: "signed"; text: string; message: string } | { kind: "error"; message: string }>(null);
  const frame = useMemo(() => textFrame(matrix, obj), [matrix, obj]);
  const background = useMemo(() => sampleBackground(canvas, matrix, obj), [canvas, matrix, obj]);

  useEffect(() => {
    let alive = true;
    previewFontFamily(page, obj).then((f) => alive && setFamily(f));
    return () => {
      alive = false;
    };
  }, [page, obj]);

  const ratio = useMemo(() => (family ? fitRatio(obj.content.text ?? "", frame, family) : 1), [family, frame, obj]);

  async function commit(text: string, extra: Record<string, unknown> = {}) {
    setBusy(true);
    setPrompt(null);
    const result = await actions.replaceText(pageId, obj, text, extra, { family: family ?? undefined, ratio, background });
    setBusy(false);
    if (result.status === "needs_confirmation") setPrompt({ kind: "fit", text, ...result });
    else if (result.status === "needs_signature_confirmation") setPrompt({ kind: "signed", text, message: result.message });
    else if (result.status === "failed") setPrompt({ kind: "error", message: result.message });
    else useSelection.getState().select({ pageId, objectId: obj.id });
  }

  function onTab(backwards: boolean, text: string) {
    if (text !== obj.content.text) void commit(text);
    // Move to the next/previous editable run in reading order (table-cell navigation, §17.2).
    const runs = scene.objects.filter((o) => o.editable && o.type === "TEXT_NATIVE")
      .sort((a, b) => b.bbox[3] - a.bbox[3] || a.bbox[0] - b.bbox[0]);
    const index = runs.findIndex((o) => o.id === obj.id);
    const next = runs[(index + (backwards ? -1 : 1) + runs.length) % runs.length];
    if (next) useSelection.getState().startEditing({ pageId, objectId: next.id }, next.content.text?.length ?? 0);
  }

  if (!family) return null;
  if (prompt) {
    const screen = pdfRectToViewport(matrix, obj.bbox);
    return (
      <>
        <TextPreview frame={frame} family={family} ratio={ratio} background={background}
          text={prompt.kind === "error" ? obj.content.text ?? "" : prompt.text} />
        <ConfirmBubble x={screen[0]} y={screen[3] + 6} onDismiss={() => useSelection.getState().stopEditing()}
          message={prompt.kind === "fit"
            ? `The new text needs ${Math.round(prompt.required)} pt but only ${Math.round(prompt.available)} pt are free without visibly squeezing it.`
            : prompt.kind === "signed" ? prompt.message : prompt.message}
          actions={prompt.kind === "fit"
            ? [{ label: "Place anyway", primary: true, run: () => commit(prompt.text, { allow_overflow: true }) },
               { label: "Keep editing", run: () => setPrompt(null) }]
            : prompt.kind === "signed"
              ? [{ label: "Edit and invalidate signature", primary: true, run: () => commit(prompt.text, { confirm_invalidate_signature: true }) },
                 { label: "Cancel", run: () => useSelection.getState().stopEditing() }]
              : [{ label: "Close", run: () => useSelection.getState().stopEditing() }]} />
      </>
    );
  }
  return (
    <InlineTextEditor obj={obj} frame={frame} family={family} ratio={ratio} background={background} caret={caret}
      busy={busy} onCommit={(text) => commit(text)} onCancel={() => useSelection.getState().stopEditing()} onTab={onTab} />
  );
}

/** "Add text" draft: style comes from the nearest text on the page (§33 nearby peers). */
function DraftEditor({ scene, point, matrix, pageId, actions }: {
  scene: PageScene; point: [number, number]; matrix: Matrix; pageId: string; actions: Actions;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const done = useRef(false);
  const peer = useMemo(() => {
    let best: SceneObject | undefined;
    let distance = Infinity;
    for (const obj of scene.objects) {
      if (obj.type !== "TEXT_NATIVE" || !obj.editable) continue;
      const [x0, y0, x1, y1] = obj.bbox;
      const d = Math.hypot(Math.max(x0 - point[0], 0, point[0] - x1), Math.max(y0 - point[1], 0, point[1] - y1));
      if (d < distance) [best, distance] = [obj, d];
    }
    return distance < 200 ? best : undefined;
  }, [scene, point]);
  const style = {
    size_pt: Number(peer?.style.size_pt ?? 11), fill: (peer?.style.fill as string) ?? "#000000",
    font_family: (peer?.style.font_family as string) ?? "Liberation Sans", bold: !!peer?.style.bold,
    italic: !!peer?.style.italic, serif: !!peer?.style.serif,
  };
  const frame = {
    transform: cssMatrix(textFrameToViewport(matrix, point, 0)), size: style.size_pt, ascent: style.size_pt * 0.9,
    descent: style.size_pt * -0.22, advance: 0, align: "left" as const, color: style.fill, weight: style.bold ? 700 : 400,
    italic: style.italic, letterSpacing: 0,
  };
  useEffect(() => {
    done.current = false;
    ref.current?.focus();
  }, []);

  function finish(commit: boolean) {
    if (done.current) return;
    done.current = true;
    const text = (ref.current?.textContent ?? "").replace(/ /g, " ").trim();
    useSelection.getState().setDraft(null);
    if (commit && text) void actions.addText(pageId, point, text, style);
  }

  return (
    <div style={{ position: "absolute", left: 0, top: 0, transform: frame.transform, transformOrigin: "0 0", zIndex: 4 }}>
      <Mask frame={{ ...frame, advance: 0 }} background="transparent" />
      <div ref={ref} role="textbox" aria-label="New text" contentEditable suppressContentEditableWarning spellCheck={false}
        className="inline-editor"
        style={{ ...textStyle(frame, `"${style.font_family}", ${style.serif ? "serif" : "sans-serif"}`, 1), minWidth: 24,
          boxShadow: "0 0 0 1px rgb(37 99 235 / 0.9)", background: "rgb(255 255 255 / 0.6)" }}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") { e.preventDefault(); finish(true); }
          if (e.key === "Escape") { e.preventDefault(); finish(false); }
        }}
        onBlur={() => finish(true)} />
    </div>
  );
}
