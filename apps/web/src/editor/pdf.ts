/** PDF.js is the visual reference layer only (architecture §31, §81 Decision 2). */
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { SceneObject } from "@folio/scene-schema";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

type LoadingTask = ReturnType<typeof pdfjs.getDocument>;
const cache = new Map<string, LoadingTask>();

export function revisionUrl(documentId: string, revision: number): string {
  return `/api/v1/documents/${documentId}/revisions/${revision}/file`;
}

/** Load one immutable revision. Keeps at most the two most recent revisions per document alive. */
export function loadRevision(documentId: string, revision: number): Promise<PDFDocumentProxy> {
  const key = `${documentId}:${revision}`;
  let task = cache.get(key);
  if (!task) {
    task = pdfjs.getDocument({
      url: revisionUrl(documentId, revision),
      withCredentials: true,
      enableXfa: false, // PDF.js never evaluates document scripts; XFA forms stay off as well (§89B.2)
      fontExtraProperties: true,
    });
    cache.set(key, task);
    const stale = [...cache.keys()].filter((k) => k.startsWith(`${documentId}:`) && k !== key);
    for (const old of stale.slice(0, Math.max(0, stale.length - 1))) {
      void cache.get(old)?.destroy();
      cache.delete(old);
    }
    const current = task;
    current.promise.catch(() => cache.get(key) === current && cache.delete(key));
  }
  return task.promise;
}

export function releaseDocument(documentId: string): void {
  for (const key of [...cache.keys()]) {
    if (key.startsWith(`${documentId}:`)) {
      void cache.get(key)?.destroy();
      cache.delete(key);
    }
  }
}

const fontCache = new WeakMap<PDFPageProxy, Promise<Array<{ x: number; y: number; font: string }>>>();

/**
 * CSS font-family for the inline editor preview. PDF.js registers each embedded font as a FontFace
 * named by its `loadedName`; matching the scene run to the PDF.js text item at the same baseline
 * lets the preview type with the document's own font. Missing subset glyphs fall back to a
 * similar generic family; the canonical result is always the backend revision (§12.2).
 */
export async function previewFontFamily(page: PDFPageProxy, obj: SceneObject): Promise<string> {
  const style = obj.style;
  const generic = style.mono ? "monospace" : style.serif ? "serif" : "sans-serif";
  const family = style.font_family ? `"${String(style.font_family).replace(/"/g, "")}", ` : "";
  const origin = obj.content.baseline_origin;
  if (!origin) return `${family}${generic}`;
  let items = fontCache.get(page);
  if (!items) {
    items = page.getTextContent().then((content) =>
      content.items.flatMap((item) =>
        "transform" in item && item.str.trim() ? [{ x: item.transform[4], y: item.transform[5], font: item.fontName }] : [],
      ),
    );
    fontCache.set(page, items);
  }
  const list = await items;
  let best: { font: string; d: number } | null = null;
  for (const item of list) {
    const d = Math.hypot(item.x - origin[0], item.y - origin[1]);
    if (d < 3 && (!best || d < best.d)) best = { font: item.font, d };
  }
  if (best && document.fonts.check(`12px "${best.font}"`)) return `"${best.font}", ${family}${generic}`;
  return `${family}${generic}`;
}
