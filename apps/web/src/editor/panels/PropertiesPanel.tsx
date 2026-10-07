import type { DocumentDetail, PageScene, SceneObject } from "@folio/scene-schema";
import { AlertTriangle, History, ShieldAlert } from "lucide-react";
import { formatBytes } from "../../api/client";
import { useRevisions, useScene } from "../../api/queries";
import { useJobs, usePanels, useSelection } from "../stores";
import type { useEditActions } from "../useEditActions";

const SOURCE: Record<string, string> = {
  PDF_NATIVE: "Native PDF", OCR_DERIVED: "OCR", VISION_DERIVED: "Vision", USER_CREATED: "Added",
  ANNOTATION_NATIVE: "Annotation", RASTER_RECONSTRUCTED: "Reconstructed",
};

const KIND: Record<string, string> = { original: "Original", edit: "Edit", undo: "Undo", redo: "Redo", restore: "Restore" };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <dt className="muted shrink-0">{label}</dt>
      <dd className="text-right truncate">{children}</dd>
    </div>
  );
}

function TextProperties({ obj }: { obj: SceneObject }) {
  const s = obj.style;
  const result = useJobs((j) => j.lastResult);
  const outcome = result?.outcome.outcomes?.find((o) => o.object_id === obj.id);
  const substitution = outcome?.substitutions.find((x) => x.reason !== "same_family_installed");
  return (
    <section className="space-y-2">
      <h2 className="font-semibold">Text</h2>
      <dl>
        <Row label="Font"><span title={String(s.font_name)}>{String(s.font_family || s.font_name)}</span></Row>
        <Row label="Size">{Number(s.size_pt).toFixed(2).replace(/\.?0+$/, "")} pt</Row>
        <Row label="Style">{[s.bold && "Bold", s.italic && "Italic"].filter(Boolean).join(", ") || "Regular"}</Row>
        <Row label="Colour">
          <span className="inline-flex items-center gap-2">
            <span className="inline-block size-3.5 rounded border border-[var(--chrome-border)]" style={{ background: String(s.fill ?? s.stroke) }} />
            {String(s.fill ?? s.stroke)}
          </span>
        </Row>
        <Row label="Alignment">{String(s.text_align ?? "left")}</Row>
        {Number(s.rotation_deg) !== 0 && <Row label="Rotation">{Number(s.rotation_deg)}°</Row>}
        {Math.abs(Number(s.letter_spacing_pt)) >= 0.05 && <Row label="Character spacing">{Number(s.letter_spacing_pt).toFixed(2)} pt</Row>}
        {Number(s.opacity ?? 1) < 1 && <Row label="Opacity">{Math.round(Number(s.opacity) * 100)}%</Row>}
        <Row label="Source">{SOURCE[obj.source] ?? obj.source}</Row>
      </dl>
      <p className="muted text-xs">Match original style is on: edits keep this font, size, colour and alignment.</p>
      {substitution && (
        <p className="text-xs flex gap-2 rounded-md p-2 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden />
          <span>The original font does not contain “{substitution.chars}”. Used the closest match ({substitution.used_font}).</span>
        </p>
      )}
      {outcome?.warnings.includes("text_adjusted_to_fit") && (
        <p className="text-xs muted">Text adjusted to fit the original space.</p>
      )}
    </section>
  );
}

function DocumentProperties({ detail, actions }: { detail: DocumentDetail; actions: ReturnType<typeof useEditActions> }) {
  const revisions = useRevisions(detail.id, true).data ?? [];
  const info = detail.info as { signed?: boolean; active_content?: string[]; metadata?: Record<string, string> };
  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-semibold mb-1">Document</h2>
        <dl>
          <Row label="Pages">{detail.page_count}</Row>
          <Row label="Size">{formatBytes(detail.size)}</Row>
          <Row label="Version">{detail.current_revision}</Row>
          {info.metadata?.title && <Row label="Title">{info.metadata.title}</Row>}
          {info.metadata?.author && <Row label="Author">{info.metadata.author}</Row>}
        </dl>
      </div>
      {info.signed && (
        <p className="text-xs flex gap-2 rounded-md p-2 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <ShieldAlert size={14} className="shrink-0 mt-0.5" aria-hidden />
          This document is digitally signed. Editing will invalidate the signature; the signed original is kept.
        </p>
      )}
      {!!info.active_content?.length && (
        <p className="text-xs muted">This file contains embedded actions ({info.active_content.join(", ")}). They are never run.</p>
      )}
      <div>
        <h2 className="font-semibold mb-1 flex items-center gap-1.5"><History size={14} aria-hidden /> History</h2>
        <ol className="space-y-0.5 max-h-72 overflow-y-auto">
          {revisions.map((r) => (
            <li key={r.revision} className="flex items-center gap-2 py-1">
              <span className={`size-1.5 rounded-full ${r.current ? "bg-[var(--color-brand-500)]" : "bg-[var(--chrome-border)]"}`} />
              <span className="flex-1">
                {KIND[r.kind] ?? r.kind} <span className="muted">· v{r.revision} · {new Date(r.created_at).toLocaleTimeString()}</span>
              </span>
              {!r.current && (
                <button className="text-xs underline muted hover:text-[var(--chrome-text)]" onClick={() => actions.restore(r.revision)}>
                  Restore
                </button>
              )}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Diagnostics({ documentId, pageId, version, objectId }: { documentId: string; pageId: string; version: number; objectId: string | null }) {
  const scene = useScene(documentId, pageId, version, true, true).data as PageScene | undefined;
  const obj = objectId ? scene?.objects.find((o) => o.id === objectId) : undefined;
  if (!scene) return null;
  const counts = scene.objects.reduce<Record<string, number>>((acc, o) => ({ ...acc, [o.type]: (acc[o.type] ?? 0) + 1 }), {});
  return (
    <section className="space-y-2 border-t border-[var(--chrome-border)] pt-3">
      <h2 className="font-semibold">Diagnostics</h2>
      <p className="text-xs muted">Page type {scene.page_type} · analyzer {scene.analyzer_version} · v{scene.page_version}</p>
      <p className="text-xs muted">{Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
      {obj && <pre className="text-[11px] leading-4 overflow-auto max-h-80 p-2 rounded bg-[var(--hover)]">{JSON.stringify(obj, null, 1)}</pre>}
    </section>
  );
}

export function PropertiesPanel({ detail, actions }: { detail: DocumentDetail; actions: ReturnType<typeof useEditActions> }) {
  const selection = useSelection((s) => s.selection);
  const developer = usePanels((s) => s.developer);
  const page = selection ? detail.pages.find((p) => p.page_id === selection.pageId) : undefined;
  const scene = useScene(detail.id, page?.page_id, page?.version, !!page).data;
  const obj = selection && scene ? scene.objects.find((o) => o.id === selection.objectId) : undefined;
  const diagnosticsPage = page ?? detail.pages[0];
  return (
    <aside className="chrome border-l w-[300px] shrink-0 overflow-y-auto p-4 space-y-4" aria-label="Properties">
      {obj?.type === "TEXT_NATIVE" ? <TextProperties obj={obj} />
        : obj ? <section><h2 className="font-semibold">{obj.type.replace(/_/g, " ").toLowerCase()}</h2>
            <p className="muted text-xs mt-1">Source: {SOURCE[obj.source] ?? obj.source}</p></section>
          : <DocumentProperties detail={detail} actions={actions} />}
      {developer && diagnosticsPage && (
        <Diagnostics documentId={detail.id} pageId={diagnosticsPage.page_id} version={diagnosticsPage.version} objectId={obj?.id ?? null} />
      )}
    </aside>
  );
}
