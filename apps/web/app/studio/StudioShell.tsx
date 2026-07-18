"use client";
import { useEffect } from "react";
import {
  ChevronLeft,
  Command,
  Copy,
  Download,
  Moon,
  PanelLeft,
  PanelRight,
  Plus,
  Redo2,
  RotateCw,
  Save,
  Scissors,
  Sun,
  Trash2,
  Undo2,
} from "lucide-react";
import { Canvas } from "./Canvas";
import { CommandPalette } from "./CommandPalette";
import { Home } from "./Home";
import { Inspector } from "./Inspector";
import { LeftNav } from "./LeftNav";
import { Ribbon } from "./Ribbon";
import { StatusBar } from "./StatusBar";
import { useStudio } from "./useStudio";
import type { StudioApi } from "./useStudio";
import type { Capability, VaultFile } from "../types";

function OrganizeGrid({ s }: { s: StudioApi }) {
  const count = s.documentInfo?.page_count ?? 0;
  return (
    <div className="sd-organize">
      <div className="sd-organize-grid">
        {Array.from({ length: count }, (_, i) => i + 1).map((n, index) => {
          const info = s.documentInfo?.pages[n - 1];
          const selected = s.page === n;
          return (
            <div
              key={n}
              className={`sd-org-tile${selected ? " active" : ""}`}
              draggable
              onDragStart={(e) => e.dataTransfer.setData("text/plain", String(n))}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const from = Number(e.dataTransfer.getData("text/plain"));
                if (from) s.reorderPage(from, index);
              }}
              onClick={() => s.setPage(n)}
            >
              <div className="sd-org-frame" style={info ? { aspectRatio: `${info.width}/${info.height}` } : undefined}>
                {selected && s.pageImage ? <img src={s.pageImage} alt={`Page ${n}`} /> : <span>{n}</span>}
              </div>
              <small>Page {n}</small>
            </div>
          );
        })}
      </div>
      <div className="sd-org-actions">
        <span>Page {s.page}</span>
        <button onClick={() => s.movePage(-1)} title="Move left"><ChevronLeft /></button>
        <button onClick={() => s.movePage(1)} title="Move right"><RotateCw style={{ transform: "scaleX(-1)" }} /></button>
        <button onClick={() => s.pageAction("rotate")} title="Rotate 90°"><RotateCw /></button>
        <button onClick={() => s.pageAction("duplicate")} title="Duplicate page"><Copy /></button>
        <button onClick={() => s.pageAction("blank")} title="Insert blank after"><Plus /></button>
        <button onClick={() => s.runJob("pdf.extract_pages", "pdf", { pages: String(s.page) })} title="Extract page"><Scissors /></button>
        <button onClick={() => { if (s.documentInfo && s.documentInfo.page_count > 1 && window.confirm(`Delete page ${s.page}? Undo can restore it before export.`)) s.pageAction("delete"); }} title="Delete page"><Trash2 /></button>
      </div>
    </div>
  );
}

function CompareView({ s }: { s: StudioApi }) {
  if (!s.comparison)
    return (
      <div className="sd-compare-empty">
        <p>Choose a second PDF in the right panel and run a comparison to see differences here.</p>
      </div>
    );
  return (
    <div className={`sd-compare ${s.comparisonMode}`}>
      {s.comparisonMode === "overlay"
        ? s.comparisonImages.overlay && <img src={s.comparisonImages.overlay} alt="Difference overlay" />
        : (
          <>
            {s.comparisonImages.before && <img src={s.comparisonImages.before} alt="Original" />}
            {s.comparisonImages.after && <img src={s.comparisonImages.after} alt="Compared" />}
          </>
        )}
    </div>
  );
}

function TitleBar({ s }: { s: StudioApi }) {
  return (
    <header className="sd-titlebar">
      <button className="sd-back" onClick={() => s.setProject(null)} title="Back to home"><ChevronLeft /> Home</button>
      <div className="sd-title-meta">
        <b>{s.project?.name}</b>
        <small>Revision {s.workspaceSession?.revision ?? s.project?.revision} · {s.operations.length} edits · {s.workspaceSession?.status ?? s.project?.status}</small>
      </div>
      <div className="sd-title-actions">
        <button className="sd-icon" title="Toggle pages panel" onClick={() => s.setLeftCollapsed(!s.leftCollapsed)}><PanelLeft /></button>
        <button className="sd-icon" title="Undo" disabled={!s.operations.length} onClick={() => s.historyAction("undo")}><Undo2 /></button>
        <button className="sd-icon" title="Redo" disabled={!s.workspaceSession} onClick={() => s.historyAction("redo")}><Redo2 /></button>
        <button className="sd-btn" disabled={s.busy} onClick={s.saveProject}><Save /> Save</button>
        <button className="sd-btn" disabled={s.busy} title="Save a new version" onClick={s.saveProject}><Copy /> Version</button>
        <button className="sd-btn sd-primary" disabled={s.busy} onClick={s.publish}><Download /> Export</button>
        <button className="sd-icon" title="Command palette (Ctrl+K)" onClick={() => s.setPaletteOpen(true)}><Command /></button>
        <button className="sd-icon" title="Toggle theme" onClick={() => s.setTheme(s.theme === "dark" ? "light" : "dark")}>{s.theme === "dark" ? <Sun /> : <Moon />}</button>
        <button className="sd-icon" title="Toggle properties panel" onClick={() => s.setRightCollapsed(!s.rightCollapsed)}><PanelRight /></button>
      </div>
    </header>
  );
}

export function StudioShell({
  files,
  capabilities,
  onJobsChanged,
}: {
  files: VaultFile[];
  capabilities: Capability[];
  onJobsChanged: () => Promise<void>;
}) {
  const s = useStudio(files, capabilities, onJobsChanged);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      const mod = event.ctrlKey || event.metaKey;
      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault();
        s.setPaletteOpen(!s.paletteOpen);
        return;
      }
      if (typing) return;
      if (event.key === "Escape") {
        s.setSelection(null);
        s.setInlineEdit(null);
        s.setTool("select");
        s.setPaletteOpen(false);
      }
      if (mod && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void s.saveProject();
      }
      if (mod && event.key.toLowerCase() === "z") {
        event.preventDefault();
        void s.historyAction("undo");
      }
      if (mod && event.key.toLowerCase() === "y") {
        event.preventDefault();
        void s.historyAction("redo");
      }
      if ((event.key === "Delete" || event.key === "Backspace") && s.selection) {
        event.preventDefault();
        if (s.selection.kind === "image") void s.editExistingImage(s.selection.object, "delete");
        else if (s.selection.kind === "vector") void s.editExistingVector(s.selection.object, "delete");
        else if (s.selection.kind === "form_field") void s.editExistingFormField(s.selection.object, "delete");
        else if (s.selection.kind === "link") void s.editExistingLink(s.selection.object, "delete");
        else if (s.selection.kind === "annotation" && s.selectedAnnotation) void s.deleteAnnotation(s.selectedAnnotation);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s.paletteOpen, s.selection, s.selectedAnnotation]);

  const notice = s.notice ? (
    <div className={`sd-notice ${s.noticeTone}`} onClick={() => s.setNotice("")}>{s.notice}</div>
  ) : null;

  if (!s.project)
    return (
      <div className="sd-root" data-sd-theme={s.theme} data-sd-density={s.density}>
        {notice}
        <Home s={s} />
      </div>
    );

  return (
    <div className="sd-root sd-workspace" data-sd-theme={s.theme} data-sd-density={s.density}>
      <TitleBar s={s} />
      <Ribbon s={s} />
      {notice}
      {s.documentInfo?.has_signatures && (
        <div className="sd-signature-warn">
          This PDF has a digital signature. Editing preserves the original, but the exported copy cannot retain the original signature validity.
        </div>
      )}
      <div className="sd-body">
        {!s.leftCollapsed && <LeftNav s={s} />}
        <main className="sd-main">
          {s.workMode === "organize" ? (
            <OrganizeGrid s={s} />
          ) : s.workMode === "compare" ? (
            <CompareView s={s} />
          ) : (
            <Canvas s={s} />
          )}
          <StatusBar s={s} />
        </main>
        {!s.rightCollapsed && <Inspector s={s} />}
      </div>
      <CommandPalette s={s} />
    </div>
  );
}
