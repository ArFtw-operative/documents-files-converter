"use client";
import {
  ChevronRight,
  Combine,
  FileText,
  GitCompare,
  Minimize2,
  Plus,
  ScanLine,
  Shield,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { StudioApi, WorkMode } from "./useStudio";

const QUICK: { label: string; icon: LucideIcon; mode: WorkMode }[] = [
  { label: "Compress", icon: Minimize2, mode: "convert" },
  { label: "OCR / Scan", icon: ScanLine, mode: "ocr" },
  { label: "Combine", icon: Combine, mode: "convert" },
  { label: "Compare", icon: GitCompare, mode: "compare" },
  { label: "Protect", icon: Shield, mode: "protect" },
];

export function Home({ s }: { s: StudioApi }) {
  async function open(mode: WorkMode = "view") {
    if (!s.sourceId) return;
    await s.createProject(s.sourceId);
    s.setWorkMode(mode);
  }

  return (
    <div className="sd-home">
      <div className="sd-home-hero">
        <p className="sd-eyebrow">PDF STUDIO</p>
        <h1>One workspace for every PDF task</h1>
        <p className="sd-home-sub">
          Edit text and images directly on the page, comment, organise, redact,
          compare, and export — non-destructively. Your original file is always kept.
        </p>
        <div className="sd-home-open">
          <select value={s.sourceId} onChange={(e) => s.setSourceId(e.target.value)}>
            <option value="">Choose a PDF from your library…</option>
            {s.pdfs.map((f) => <option key={f.id} value={f.id}>{f.display_name}</option>)}
          </select>
          <button className="sd-primary" disabled={!s.sourceId || s.busy} onClick={() => open("view")}>
            <Plus /> Open in editor
          </button>
        </div>
        {!s.pdfs.length && <p className="sd-warn">Upload a PDF in Convert or Library first.</p>}
        <div className="sd-quick">
          {QUICK.map((q) => {
            const Icon = q.icon;
            return (
              <button key={q.label} className="sd-quick-tile" disabled={!s.sourceId || s.busy} title={!s.sourceId ? "Choose a PDF first" : q.label} onClick={() => open(q.mode)}>
                <Icon /><span>{q.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="sd-home-recent">
        <p className="sd-panel-title">Recent projects</p>
        {s.projects.length ? (
          <div className="sd-recent-list">
            {s.projects.map((p) => (
              <button key={p.id} className="sd-recent" onClick={() => s.setProject(p)}>
                <FileText />
                <span><b>{p.name}</b><small>Revision {p.revision} · {p.status}</small></span>
                <ChevronRight />
              </button>
            ))}
          </div>
        ) : (
          <p className="sd-empty">No projects yet. Open a PDF above to start.</p>
        )}
      </div>
    </div>
  );
}
