import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PageInfo } from "@folio/scene-schema";
import { api } from "../../api/client";
import { CSS_UNITS, useSelection, useTool, useViewport } from "../stores";
import type { useEditActions } from "../useEditActions";
import { PageView } from "./PageView";

const GAP = 16;
const PADDING = 24;

export function displaySize(page: PageInfo): { w: number; h: number } {
  const w = page.width_pt ?? 595;
  const h = page.height_pt ?? 842;
  return (page.rotation ?? 0) % 180 === 0 ? { w, h } : { w: h, h: w };
}

interface Props {
  documentId: string;
  pages: PageInfo[];
  pdf: PDFDocumentProxy;
  revision: number;
  actions: ReturnType<typeof useEditActions>;
}

export function DocumentCanvas({ documentId, pages, pdf, revision, actions }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const { zoom, fit, scrollToPage } = useViewport();
  const tool = useTool((s) => s.tool);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setContainerWidth(el.clientWidth));
    observer.observe(el);
    setContainerWidth(el.clientWidth);
    return () => observer.disconnect();
  }, []);

  const maxWidth = useMemo(() => Math.max(...pages.map((p) => displaySize(p).w), 1), [pages]);
  const maxHeight = useMemo(() => Math.max(...pages.map((p) => displaySize(p).h), 1), [pages]);
  const scale = useMemo(() => {
    if (!containerWidth) return zoom * CSS_UNITS;
    if (fit === "width") return Math.max(0.2, (containerWidth - PADDING * 2) / maxWidth);
    if (fit === "page") {
      const height = (scroller.current?.clientHeight ?? 800) - PADDING * 2;
      return Math.max(0.2, Math.min((containerWidth - PADDING * 2) / maxWidth, height / maxHeight));
    }
    return zoom * CSS_UNITS;
  }, [containerWidth, fit, zoom, maxWidth, maxHeight]);

  // Expose the effective zoom (for the status bar) when fitting.
  useEffect(() => {
    if (fit) useViewport.setState({ zoom: scale / CSS_UNITS });
  }, [fit, scale]);

  const virtualizer = useVirtualizer({
    count: pages.length,
    getScrollElement: () => scroller.current,
    estimateSize: (i) => displaySize(pages[i]).h * scale + GAP,
    overscan: 2,
    paddingStart: PADDING,
    paddingEnd: PADDING,
  });

  useEffect(() => virtualizer.measure(), [scale, pages, virtualizer]);

  useEffect(() => {
    if (scrollToPage === null) return;
    virtualizer.scrollToIndex(scrollToPage, { align: "start" });
    useViewport.getState().requestScroll(null);
  }, [scrollToPage, virtualizer]);

  const items = virtualizer.getVirtualItems();

  // Current page = the page covering the viewport centre.
  useEffect(() => {
    const el = scroller.current;
    if (!el || !items.length) return;
    const centre = el.scrollTop + el.clientHeight / 2;
    const current = items.find((item) => item.start <= centre && item.end >= centre) ?? items[0];
    if (current.index !== useViewport.getState().currentPage) useViewport.getState().setCurrentPage(current.index);
  });

  // Visible pages jump the background analysis queue (§21 P1/P2, §50).
  const visibleKey = items.map((i) => pages[i.index]?.page_id).join(",");
  useEffect(() => {
    const ids = items.map((i) => pages[i.index]).filter((p) => p && p.analysis_status === "pending").map((p) => p.page_id);
    if (!ids.length) return;
    const timer = window.setTimeout(() => {
      api(`/api/v1/documents/${documentId}/analyze`, { json: { page_ids: ids, priority: "visible" } }).catch(() => undefined);
    }, 150);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleKey, documentId]);

  // Ctrl/Cmd + wheel zooms around the pointer.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      const current = useViewport.getState().zoom;
      useViewport.getState().setZoom(current * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Hand tool: drag to pan.
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  return (
    <div
      ref={scroller}
      className="flex-1 min-w-0 overflow-auto relative outline-none"
      style={{ background: "var(--canvas-bg)", cursor: tool === "pan" ? (drag.current ? "grabbing" : "grab") : undefined }}
      tabIndex={-1}
      onPointerDown={(e) => {
        if (tool !== "pan" || !scroller.current) return;
        drag.current = { x: e.clientX, y: e.clientY, left: scroller.current.scrollLeft, top: scroller.current.scrollTop };
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => {
        if (!drag.current || !scroller.current) return;
        scroller.current.scrollLeft = drag.current.left - (e.clientX - drag.current.x);
        scroller.current.scrollTop = drag.current.top - (e.clientY - drag.current.y);
      }}
      onPointerUp={() => (drag.current = null)}
      onClick={(e) => {
        if (e.target === e.currentTarget) useSelection.getState().select(null);
      }}
    >
      <div style={{ height: virtualizer.getTotalSize(), minWidth: maxWidth * scale + PADDING * 2, position: "relative" }}
        onClick={(e) => e.target === e.currentTarget && useSelection.getState().select(null)}>
        {items.map((item) => {
          const page = pages[item.index];
          const { w, h } = displaySize(page);
          return (
            <div key={page.page_id} style={{ position: "absolute", top: item.start, left: 0, right: 0, display: "flex",
              justifyContent: "center", padding: `0 ${PADDING}px` }}>
              <PageView documentId={documentId} info={page} pdf={pdf} revision={revision} scale={scale}
                width={Math.round(w * scale)} height={Math.round(h * scale)} actions={actions} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
