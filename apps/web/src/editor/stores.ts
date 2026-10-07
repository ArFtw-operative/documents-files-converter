/**
 * High-frequency editor state (architecture §51): Zustand. Server state stays in TanStack Query.
 */
import { create } from "zustand";
import type { BatchResult } from "@folio/scene-schema";

export type Tool = "select" | "edit" | "addText" | "pan";

export const ZOOM_PRESETS = [0.5, 0.75, 1, 1.25, 1.5, 2, 4] as const;
/** PDF.js scale for "100%": 1pt = 96/72 CSS px (actual size on a standard display). */
export const CSS_UNITS = 96 / 72;

interface ViewportState {
  zoom: number;
  fit: "width" | "page" | null;
  currentPage: number;
  scrollToPage: number | null;
  setZoom: (zoom: number) => void;
  setFit: (fit: "width" | "page") => void;
  setCurrentPage: (page: number) => void;
  requestScroll: (page: number | null) => void;
}

export const useViewport = create<ViewportState>((set) => ({
  zoom: 1,
  fit: "width",
  currentPage: 0,
  scrollToPage: null,
  setZoom: (zoom) => set({ zoom: Math.min(4, Math.max(0.25, zoom)), fit: null }),
  setFit: (fit) => set({ fit }),
  setCurrentPage: (currentPage) => set({ currentPage }),
  requestScroll: (scrollToPage) => set({ scrollToPage }),
}));

export interface ObjectRef {
  pageId: string;
  objectId: string;
}

interface SelectionState {
  hover: ObjectRef | null;
  selection: ObjectRef | null;
  editing: (ObjectRef & { caret: number }) | null;
  draft: { pageId: string; point: [number, number] } | null;
  /** Alt+click cycling through overlapping candidates. */
  cycle: { key: string; index: number } | null;
  setHover: (ref: ObjectRef | null) => void;
  select: (ref: ObjectRef | null) => void;
  startEditing: (ref: ObjectRef, caret: number) => void;
  stopEditing: () => void;
  setDraft: (draft: SelectionState["draft"]) => void;
  setCycle: (cycle: SelectionState["cycle"]) => void;
}

export const useSelection = create<SelectionState>((set) => ({
  hover: null,
  selection: null,
  editing: null,
  draft: null,
  cycle: null,
  setHover: (hover) => set({ hover }),
  select: (selection) => set({ selection, editing: null }),
  startEditing: (ref, caret) => set({ selection: ref, editing: { ...ref, caret }, draft: null }),
  stopEditing: () => set({ editing: null }),
  setDraft: (draft) => set({ draft, editing: null, selection: null }),
  setCycle: (cycle) => set({ cycle }),
}));

interface ToolState {
  tool: Tool;
  setTool: (tool: Tool) => void;
}

export const useTool = create<ToolState>((set) => ({ tool: "edit", setTool: (tool) => set({ tool }) }));

/** Optimistic text shown until the canonical PDF revision containing it has rendered (§12.2). */
export interface PendingText {
  pageId: string;
  objectId: string;
  text: string;
  untilRevision: number | null; // null while the commit is in flight
  family?: string;
  ratio?: number;
  background?: string;
}

export type SaveState = "idle" | "saving" | "saved" | "failed" | "offline";

interface JobState {
  saveState: SaveState;
  saveMessage: string | null;
  savedAt: number | null;
  lastResult: BatchResult | null;
  pending: Record<string, PendingText>;
  analysis: "idle" | "running";
  setSave: (state: SaveState, message?: string | null) => void;
  setResult: (result: BatchResult | null) => void;
  putPending: (pending: PendingText) => void;
  settlePending: (pageId: string, renderedRevision: number) => void;
  dropPending: (objectId: string) => void;
  setAnalysis: (state: "idle" | "running") => void;
}

export const useJobs = create<JobState>((set) => ({
  saveState: "idle",
  saveMessage: null,
  savedAt: null,
  lastResult: null,
  pending: {},
  analysis: "idle",
  setSave: (saveState, saveMessage = null) =>
    set((s) => ({ saveState, saveMessage, savedAt: saveState === "saved" ? Date.now() : s.savedAt })),
  setResult: (lastResult) => set({ lastResult }),
  putPending: (pending) => set((s) => ({ pending: { ...s.pending, [pending.objectId]: pending } })),
  settlePending: (pageId, rendered) =>
    set((s) => {
      const next = Object.fromEntries(
        Object.entries(s.pending).filter(
          ([, p]) => p.pageId !== pageId || p.untilRevision === null || p.untilRevision > rendered),
      );
      return Object.keys(next).length === Object.keys(s.pending).length ? s : { pending: next };
    }),
  dropPending: (objectId) =>
    set((s) => {
      const next = { ...s.pending };
      delete next[objectId];
      return { pending: next };
    }),
  setAnalysis: (analysis) => set({ analysis }),
}));

interface PanelState {
  thumbnails: boolean;
  properties: boolean;
  developer: boolean;
  palette: boolean;
  toggle: (panel: "thumbnails" | "properties" | "developer" | "palette", value?: boolean) => void;
}

function stored(key: string, fallback: boolean): boolean {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value === "1";
  } catch {
    return fallback;
  }
}

export const usePanels = create<PanelState>((set) => ({
  thumbnails: stored("folio.panel.thumbnails", window.innerWidth > 900),
  properties: stored("folio.panel.properties", window.innerWidth > 1100),
  developer: stored("folio.developer", false),
  palette: false,
  toggle: (panel, value) =>
    set((s) => {
      const next = value ?? !s[panel];
      if (panel !== "palette") {
        try {
          localStorage.setItem(panel === "developer" ? "folio.developer" : `folio.panel.${panel}`, next ? "1" : "0");
        } catch {
          /* per-viewer convenience only */
        }
      }
      return { [panel]: next } as Partial<PanelState>;
    }),
}));
