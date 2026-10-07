import { useCallback, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { DocumentDetail, PageInfo, PageScene } from "@folio/scene-schema";
import { api } from "../api/client";
import { keys, useDocument, type SessionUser } from "../api/queries";
import { navigate } from "../router";
import { DocumentCanvas } from "./canvas/DocumentCanvas";
import { CommandPalette, FindBar, StatusBar, ToolRibbon, TopBar } from "./EditorChrome";
import { PropertiesPanel } from "./panels/PropertiesPanel";
import { ThumbnailRail } from "./panels/ThumbnailRail";
import { loadRevision, releaseDocument } from "./pdf";
import { usePanels, useSelection, useTool, useViewport } from "./stores";
import { useDocumentEvents } from "./useDocumentEvents";
import { useEditActions } from "./useEditActions";

/** The page snapshot being displayed. Swapped atomically once a new revision's PDF has loaded so
 * page indices, page versions and the rendered PDF always agree. */
interface View {
  revision: number;
  pages: PageInfo[];
  pdf: PDFDocumentProxy;
}

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT");
}

export default function EditorPage({ documentId }: { documentId: string; user: SessionUser }) {
  const document = useDocument(documentId);
  const detail = document.data;
  const actions = useEditActions(documentId);
  const queryClient = useQueryClient();
  const [view, setView] = useState<View | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const panels = usePanels();

  useEffect(() => () => {
    releaseDocument(documentId);
    useSelection.setState({ hover: null, selection: null, editing: null, draft: null });
  }, [documentId]);

  useEffect(() => {
    if (!detail || detail.status !== "ready" || !detail.current_revision) return;
    if (view && view.revision === detail.current_revision) {
      // Same PDF; page analysis/versions may still have changed.
      if (view.pages !== detail.pages) setView({ ...view, pages: detail.pages });
      return;
    }
    let alive = true;
    loadRevision(documentId, detail.current_revision)
      .then((pdf) => alive && setView({ revision: detail.current_revision, pages: detail.pages, pdf }))
      .catch(() => alive && setLoadError("This version of the document could not be displayed."));
    return () => {
      alive = false;
    };
  }, [detail, documentId, view]);

  const onReconnect = useCallback(() => void actions.replayPending(), [actions]);
  useDocumentEvents(documentId, onReconnect);
  useEffect(() => {
    if (detail?.status === "ready") void actions.replayPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.status]);

  // ---- find (§38)
  const [findOpen, setFindOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [hit, setHit] = useState(0);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query.trim()), 200);
    return () => window.clearTimeout(t);
  }, [query]);
  const search = useQuery({
    queryKey: ["search", documentId, detail?.current_revision, debounced],
    queryFn: () => api<{ results: Array<{ page_index: number; page_id: string; object_id: string; text: string }> }>(
      `/api/v1/documents/${documentId}/search?q=${encodeURIComponent(debounced)}`),
    enabled: findOpen && debounced.length > 0,
  });
  const results = search.data?.results ?? [];
  const goTo = useCallback((i: number) => {
    const r = results[i];
    if (!r) return;
    setHit(i);
    useViewport.getState().requestScroll(r.page_index);
    useSelection.getState().select({ pageId: r.page_id, objectId: r.object_id });
  }, [results]);
  useEffect(() => {
    if (results.length) goTo(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search.data]);
  const openFind = useCallback(() => setFindOpen(true), []);

  // ---- keyboard shortcuts (§4.10)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const mod = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (mod && key === "k") { event.preventDefault(); usePanels.getState().toggle("palette", true); return; }
      if (mod && key === "f") { event.preventDefault(); setFindOpen(true); return; }
      if (mod && key === "s") { event.preventDefault(); if (event.shiftKey) void actions.exportPdf("standard"); return; }
      if (event.key === "F4") { event.preventDefault(); usePanels.getState().toggle("properties"); return; }
      if (event.key === "F9") { event.preventDefault(); usePanels.getState().toggle("thumbnails"); return; }
      if (isTyping(event.target)) return;
      if (mod && key === "z") { event.preventDefault(); void (event.shiftKey ? actions.redo() : actions.undo()); return; }
      if (mod && key === "y") { event.preventDefault(); void actions.redo(); return; }
      if (mod && (key === "=" || key === "+")) { event.preventDefault(); useViewport.getState().setZoom(useViewport.getState().zoom * 1.2); return; }
      if (mod && key === "-") { event.preventDefault(); useViewport.getState().setZoom(useViewport.getState().zoom / 1.2); return; }
      if (mod) return;
      const tools: Record<string, Parameters<ReturnType<typeof useTool.getState>["setTool"]>[0]> = { v: "select", e: "edit", t: "addText", h: "pan" };
      if (tools[key]) { useTool.getState().setTool(tools[key]); return; }
      const { currentPage } = useViewport.getState();
      if (event.key === "PageDown") { event.preventDefault(); useViewport.getState().requestScroll(Math.min((detail?.page_count ?? 1) - 1, currentPage + 1)); }
      if (event.key === "PageUp") { event.preventDefault(); useViewport.getState().requestScroll(Math.max(0, currentPage - 1)); }
      if (event.key === "Escape") useSelection.getState().select(null);
      if (event.key === "Delete" || event.key === "Backspace") {
        const selection = useSelection.getState().selection;
        if (!selection || !detail) return;
        const page = detail.pages.find((p) => p.page_id === selection.pageId);
        const scene = page && queryClient.getQueryData<PageScene>(keys.scene(documentId, page.page_id, page.version));
        const obj = scene?.objects.find((o) => o.id === selection.objectId);
        if (obj?.editable) {
          event.preventDefault();
          void actions.deleteObject(selection.pageId, obj);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [actions, detail, documentId, queryClient]);

  if (document.isError) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3">
        <p>This document is not available.</p>
        <button className="btn" onClick={() => navigate("/")}>Back to Library</button>
      </div>
    );
  }
  if (!detail || detail.status === "processing") return <div className="h-full flex items-center justify-center muted">Preparing document…</div>;
  if (detail.status === "failed") {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 p-4 text-center">
        <p>{detail.error}</p>
        <button className="btn" onClick={() => navigate("/")}>Back to Library</button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <TopBar detail={detail} actions={actions} onFind={openFind} />
      <ToolRibbon />
      <div className="flex-1 min-h-0 flex relative">
        {panels.thumbnails && view && <ThumbnailRail pdf={view.pdf} pages={view.pages} revision={view.revision} actions={actions} />}
        {view ? (
          <DocumentCanvas documentId={documentId} pages={view.pages} pdf={view.pdf} revision={view.revision} actions={actions} />
        ) : (
          <div className="flex-1 flex items-center justify-center muted" style={{ background: "var(--canvas-bg)" }}>
            {loadError ?? "Opening…"}
          </div>
        )}
        {panels.properties && <PropertiesPanel detail={detail as DocumentDetail} actions={actions} />}
        <FindBar open={findOpen} onClose={() => { setFindOpen(false); setQuery(""); }} query={query} setQuery={setQuery}
          results={results.length} index={hit} onStep={(d) => results.length && goTo((hit + d + results.length) % results.length)} />
      </div>
      <StatusBar detail={detail} />
      <CommandPalette detail={detail} actions={actions} onFind={openFind} />
    </div>
  );
}
