import { useEffect, useMemo, useRef, useState } from "react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { DocumentDetail } from "@folio/scene-schema";
import {
  ArrowLeft, Check, ChevronDown, CloudOff, Download, Hand, Loader2, Menu as MenuIcon, MousePointer2,
  PanelLeft, PanelRight, Redo2, Search, TextCursorInput, Type, Undo2, X,
} from "lucide-react";
import { api } from "../api/client";
import { navigate } from "../router";
import { usePanels, useJobs, useTool, useViewport, ZOOM_PRESETS, type Tool } from "./stores";
import type { useEditActions } from "./useEditActions";

type Actions = ReturnType<typeof useEditActions>;

function Tip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal><Tooltip.Content className="tooltip" sideOffset={6}>{label}</Tooltip.Content></Tooltip.Portal>
    </Tooltip.Root>
  );
}

export function TopBar({ detail, actions, onFind }: { detail: DocumentDetail; actions: Actions; onFind: () => void }) {
  const panels = usePanels();
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(detail.name);
  useEffect(() => setName(detail.name), [detail.name]);

  async function rename() {
    setRenaming(false);
    if (name.trim() && name !== detail.name) {
      await api(`/api/v1/documents/${detail.id}`, { method: "PATCH", json: { name } }).catch(() => setName(detail.name));
      actions.refresh();
    }
  }

  return (
    <header className="chrome border-b h-12 flex items-center gap-1 px-2 shrink-0">
      <Menu.Root>
        <Menu.Trigger asChild>
          <button className="icon-btn" aria-label="Application menu"><MenuIcon size={17} aria-hidden /></button>
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Content className="menu" sideOffset={4} align="start">
            <Menu.Item className="menu-item" onSelect={() => navigate("/")}><ArrowLeft size={14} aria-hidden /> Back to Library</Menu.Item>
            <Menu.Separator className="menu-separator" />
            <Menu.Item className="menu-item" onSelect={() => panels.toggle("thumbnails")}>
              <PanelLeft size={14} aria-hidden /> {panels.thumbnails ? "Hide" : "Show"} pages <span className="ml-auto muted">F9</span>
            </Menu.Item>
            <Menu.Item className="menu-item" onSelect={() => panels.toggle("properties")}>
              <PanelRight size={14} aria-hidden /> {panels.properties ? "Hide" : "Show"} properties <span className="ml-auto muted">F4</span>
            </Menu.Item>
            <Menu.CheckboxItem className="menu-item" checked={panels.developer} onCheckedChange={(v) => panels.toggle("developer", !!v)}>
              <span className="w-3.5">{panels.developer && <Check size={14} aria-hidden />}</span> Developer diagnostics
            </Menu.CheckboxItem>
            <Menu.Separator className="menu-separator" />
            <Menu.Item className="menu-item" onSelect={() => panels.toggle("palette", true)}>
              Command palette <span className="ml-auto muted">Ctrl K</span>
            </Menu.Item>
          </Menu.Content>
        </Menu.Portal>
      </Menu.Root>
      <span className="font-semibold text-[13px] hidden sm:inline">Verso Folio</span>
      <span className="muted px-1 hidden sm:inline">|</span>
      {renaming ? (
        <input className="input !h-7 max-w-72" value={name} autoFocus onChange={(e) => setName(e.target.value)}
          onBlur={rename} onKeyDown={(e) => { if (e.key === "Enter") rename(); if (e.key === "Escape") { setName(detail.name); setRenaming(false); } }} />
      ) : (
        <button className="truncate max-w-[40vw] px-1.5 py-1 rounded hover:bg-[var(--hover)]" onClick={() => setRenaming(true)}
          title="Rename">{detail.name}</button>
      )}
      <SaveIndicator />
      <div className="ml-auto flex items-center gap-1">
        <Tip label="Undo (Ctrl+Z)">
          <button className="icon-btn" disabled={!detail.can_undo} onClick={actions.undo} aria-label="Undo"><Undo2 size={17} aria-hidden /></button>
        </Tip>
        <Tip label="Redo (Ctrl+Shift+Z)">
          <button className="icon-btn" disabled={!detail.can_redo} onClick={actions.redo} aria-label="Redo"><Redo2 size={17} aria-hidden /></button>
        </Tip>
        <Tip label="Find (Ctrl+F)">
          <button className="icon-btn" onClick={onFind} aria-label="Find"><Search size={17} aria-hidden /></button>
        </Tip>
        <div className="flex">
          <button className="btn btn-primary !rounded-r-none" onClick={() => actions.exportPdf("standard")}>
            <Download size={15} aria-hidden /> <span className="hidden sm:inline">Download</span>
          </button>
          <Menu.Root>
            <Menu.Trigger asChild>
              <button className="btn btn-primary !rounded-l-none !px-1.5 border-l border-l-white/30" aria-label="More download options">
                <ChevronDown size={14} aria-hidden />
              </button>
            </Menu.Trigger>
            <Menu.Portal>
              <Menu.Content className="menu" sideOffset={4} align="end">
                <Menu.Item className="menu-item" onSelect={() => actions.exportPdf("standard")}>Download PDF</Menu.Item>
                <Menu.Item className="menu-item" onSelect={() => actions.exportPdf("optimized")}>Download optimised (smaller) PDF</Menu.Item>
              </Menu.Content>
            </Menu.Portal>
          </Menu.Root>
        </div>
      </div>
    </header>
  );
}

function SaveIndicator() {
  const { saveState, saveMessage } = useJobs();
  const map = {
    idle: null,
    saving: <><Loader2 size={13} className="animate-spin" aria-hidden /> Saving…</>,
    saved: <><Check size={13} aria-hidden /> {saveMessage ?? "Saved"}</>,
    failed: <span className="text-red-700 dark:text-red-400">Save failed</span>,
    offline: <><CloudOff size={13} aria-hidden /> Offline changes</>,
  } as const;
  const content = map[saveState];
  if (!content) return null;
  return (
    <span className="muted text-xs inline-flex items-center gap-1 ml-2" role="status" title={saveMessage ?? undefined}>{content}</span>
  );
}

const TOOLS: Array<{ id: Tool; label: string; key: string; icon: typeof MousePointer2 }> = [
  { id: "select", label: "Select", key: "V", icon: MousePointer2 },
  { id: "edit", label: "Edit text", key: "E", icon: TextCursorInput },
  { id: "addText", label: "Add text", key: "T", icon: Type },
  { id: "pan", label: "Hand", key: "H", icon: Hand },
];

export function ToolRibbon() {
  const { tool, setTool } = useTool();
  return (
    <div className="chrome border-b h-11 flex items-center gap-1 px-2 shrink-0" role="toolbar" aria-label="Tools">
      {TOOLS.map(({ id, label, key, icon: Icon }) => (
        <Tip key={id} label={`${label} (${key})`}>
          <button className="icon-btn !w-auto px-2.5 gap-1.5" data-active={tool === id} aria-pressed={tool === id} onClick={() => setTool(id)}>
            <Icon size={16} aria-hidden /> <span className="hidden md:inline">{label}</span>
          </button>
        </Tip>
      ))}
    </div>
  );
}

export function StatusBar({ detail }: { detail: DocumentDetail }) {
  const { currentPage, zoom, fit, setZoom, setFit, requestScroll } = useViewport();
  const analysing = detail.pages.some((p) => p.analysis_status === "pending");
  const [pageInput, setPageInput] = useState("");
  return (
    <footer className="chrome border-t h-8 flex items-center gap-3 px-3 text-xs shrink-0">
      <label className="flex items-center gap-1.5">
        <span className="muted">Page</span>
        <input className="input !h-6 !w-12 !px-1 text-center tabular-nums" aria-label="Current page"
          value={pageInput || String(currentPage + 1)} onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ""))}
          onBlur={() => setPageInput("")}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const n = Math.min(detail.page_count, Math.max(1, Number(pageInput) || 1));
              requestScroll(n - 1);
              setPageInput("");
              (e.target as HTMLInputElement).blur();
            }
          }} />
        <span className="muted tabular-nums">/ {detail.page_count}</span>
      </label>
      <span className="w-px h-4 bg-[var(--chrome-border)]" />
      <Menu.Root>
        <Menu.Trigger asChild>
          <button className="btn !h-6 !px-2 tabular-nums" aria-label="Zoom">{Math.round(zoom * 100)}% <ChevronDown size={12} aria-hidden /></button>
        </Menu.Trigger>
        <Menu.Portal>
          <Menu.Content className="menu" side="top" sideOffset={4}>
            <Menu.Item className="menu-item" onSelect={() => setFit("width")}>Fit width {fit === "width" && <Check size={13} className="ml-auto" aria-hidden />}</Menu.Item>
            <Menu.Item className="menu-item" onSelect={() => setFit("page")}>Fit page {fit === "page" && <Check size={13} className="ml-auto" aria-hidden />}</Menu.Item>
            <Menu.Item className="menu-item" onSelect={() => setZoom(1)}>Actual size</Menu.Item>
            <Menu.Separator className="menu-separator" />
            {ZOOM_PRESETS.map((z) => (
              <Menu.Item key={z} className="menu-item" onSelect={() => setZoom(z)}>{z * 100}%</Menu.Item>
            ))}
          </Menu.Content>
        </Menu.Portal>
      </Menu.Root>
      <button className="btn !h-6 !px-2" onClick={() => setFit("width")} data-active={fit === "width"}>Fit width</button>
      <span className="ml-auto muted inline-flex items-center gap-1.5">
        {analysing ? <><Loader2 size={12} className="animate-spin" aria-hidden /> Reading pages…</> : "Ready"}
      </span>
      <span className="muted tabular-nums">v{detail.current_revision}</span>
    </footer>
  );
}

interface Command {
  label: string;
  hint?: string;
  run: () => void;
  disabled?: boolean;
}

export function CommandPalette({ detail, actions, onFind }: { detail: DocumentDetail; actions: Actions; onFind: () => void }) {
  const open = usePanels((s) => s.palette);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const page = detail.pages[useViewport.getState().currentPage];
  const commands: Command[] = useMemo(() => [
    { label: "Edit text", hint: "E", run: () => useTool.getState().setTool("edit") },
    { label: "Add text", hint: "T", run: () => useTool.getState().setTool("addText") },
    { label: "Find text", hint: "Ctrl F", run: onFind },
    { label: "Undo", hint: "Ctrl Z", run: actions.undo, disabled: !detail.can_undo },
    { label: "Redo", hint: "Ctrl Shift Z", run: actions.redo, disabled: !detail.can_redo },
    { label: "Rotate current page right", run: () => page && actions.pageOperation("rotate_page", page.page_id, { degrees: 90 }) },
    { label: "Insert blank page after current", run: () => page && actions.pageOperation("insert_page", null, { at: page.index + 1 }) },
    { label: "Download PDF", run: () => actions.exportPdf("standard") },
    { label: "Download optimised PDF", run: () => actions.exportPdf("optimized") },
    { label: "Toggle pages panel", hint: "F9", run: () => usePanels.getState().toggle("thumbnails") },
    { label: "Toggle properties panel", hint: "F4", run: () => usePanels.getState().toggle("properties") },
    { label: "View document diagnostics", run: () => { usePanels.getState().toggle("developer", true); usePanels.getState().toggle("properties", true); } },
    { label: "Back to Library", run: () => navigate("/") },
  ], [actions, detail.can_redo, detail.can_undo, onFind, page]);
  const filtered = commands.filter((c) => !c.disabled && c.label.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      setTimeout(() => input.current?.focus(), 0);
    }
  }, [open]);

  if (!open) return null;
  const close = () => usePanels.getState().toggle("palette", false);
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/20 px-4" onClick={close}>
      <div role="dialog" aria-label="Command palette" className="chrome border rounded-xl shadow-2xl w-full max-w-md overflow-hidden"
        onClick={(e) => e.stopPropagation()}>
        <input ref={input} className="w-full h-11 px-4 bg-transparent outline-none border-b border-[var(--chrome-border)]"
          placeholder="Type a command…" value={query} onChange={(e) => { setQuery(e.target.value); setIndex(0); }}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") close();
            if (e.key === "ArrowDown") setIndex((i) => Math.min(filtered.length - 1, i + 1));
            if (e.key === "ArrowUp") setIndex((i) => Math.max(0, i - 1));
            if (e.key === "Enter" && filtered[index]) { close(); filtered[index].run(); }
          }} />
        <ul className="max-h-80 overflow-y-auto p-1" role="listbox">
          {filtered.map((c, i) => (
            <li key={c.label} role="option" aria-selected={i === index}
              className={`menu-item ${i === index ? "bg-[var(--hover)]" : ""}`} onMouseEnter={() => setIndex(i)}
              onClick={() => { close(); c.run(); }}>
              {c.label}{c.hint && <span className="ml-auto muted text-xs">{c.hint}</span>}
            </li>
          ))}
          {!filtered.length && <li className="px-3 py-2 muted">No matching command</li>}
        </ul>
      </div>
    </div>
  );
}

export function FindBar({ open, onClose, query, setQuery, results, index, onStep }: {
  open: boolean; onClose: () => void; query: string; setQuery: (q: string) => void; results: number; index: number; onStep: (d: 1 | -1) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div className="chrome border rounded-lg shadow-lg absolute right-4 top-2 z-30 flex items-center gap-1 p-1">
      <input ref={input} className="input !h-7 !w-56" placeholder="Find in document" value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") onStep(e.shiftKey ? -1 : 1);
          if (e.key === "Escape") onClose();
        }} />
      <span className="muted text-xs tabular-nums px-1 min-w-12 text-center">{query ? `${results ? index + 1 : 0}/${results}` : ""}</span>
      <button className="icon-btn !size-7" onClick={onClose} aria-label="Close find"><X size={14} aria-hidden /></button>
    </div>
  );
}
