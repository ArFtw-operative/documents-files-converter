import { useRef, useState, type DragEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileText, Loader2, Trash2, Upload } from "lucide-react";
import type { DocumentDetail } from "@folio/scene-schema";
import { api, ApiError, formatBytes } from "../api/client";
import { keys, useDocuments, type SessionUser } from "../api/queries";
import { navigate } from "../router";

export function LibraryPage({ user }: { user: SessionUser }) {
  const documents = useDocuments();
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);

  async function upload(files: FileList | File[]) {
    const list = Array.from(files);
    setErrors([]);
    for (const file of list) {
      setUploading((u) => [...u, file.name]);
      try {
        const form = new FormData();
        form.append("file", file);
        const doc = await api<DocumentDetail>("/api/v1/documents", { body: form });
        if (list.length === 1 && doc.status === "ready") navigate(`/d/${doc.id}`);
      } catch (err) {
        setErrors((e) => [...e, `${file.name}: ${(err as ApiError).message}`]);
      } finally {
        setUploading((u) => u.filter((name) => name !== file.name));
        client.invalidateQueries({ queryKey: keys.documents });
      }
    }
  }

  async function remove(id: string, name: string) {
    if (!window.confirm(`Move “${name}” to the trash?`)) return;
    await api(`/api/v1/documents/${id}`, { method: "DELETE" });
    client.invalidateQueries({ queryKey: keys.documents });
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) upload(event.dataTransfer.files);
  }

  const data = documents.data;
  return (
    <div className="max-w-5xl mx-auto p-4 md:p-8 space-y-6" onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)} onDrop={onDrop}>
      <header className="flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-xl font-semibold">Library</h1>
          <p className="muted text-xs">
            {user.display_name}
            {data && ` · ${formatBytes(data.usage_bytes)} of ${formatBytes(data.quota_bytes)} used`}
          </p>
        </div>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden
          onChange={(e) => e.target.files && upload(e.target.files)} />
        <button className="btn btn-primary" onClick={() => input.current?.click()}>
          <Upload size={15} aria-hidden /> Open PDF
        </button>
      </header>

      <div className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors ${dragging ? "border-[var(--color-select)] bg-[var(--color-select-soft)]" : "border-[var(--chrome-border)]"}`}>
        <p className="muted">Drop PDF files here to open them in the editor.</p>
        {uploading.map((name) => (
          <p key={name} className="mt-2 inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" aria-hidden /> Preparing {name}…</p>
        ))}
        {errors.map((message) => (
          <p key={message} role="alert" className="mt-2 text-red-700 dark:text-red-400 inline-flex items-center gap-2">
            <AlertTriangle size={14} aria-hidden /> {message}
          </p>
        ))}
      </div>

      {documents.isLoading && <p className="muted">Loading documents…</p>}
      {data && data.documents.length === 0 && <p className="muted">No documents yet.</p>}
      {data && data.documents.length > 0 && (
        <ul className="chrome border rounded-xl divide-y divide-[var(--chrome-border)]">
          {data.documents.map((doc) => (
            <li key={doc.id} className="flex items-center gap-3 px-4 py-3">
              <FileText size={18} className="muted shrink-0" aria-hidden />
              <button className="min-w-0 flex-1 text-left" onClick={() => doc.status === "ready" && navigate(`/d/${doc.id}`)}
                disabled={doc.status !== "ready"}>
                <div className="font-medium truncate">{doc.name}</div>
                <div className="muted text-xs">
                  {doc.status === "ready" ? `${doc.page_count} page${doc.page_count === 1 ? "" : "s"} · ${formatBytes(doc.size)} · edited ${new Date(doc.updated_at).toLocaleString()}`
                    : doc.status === "failed" ? doc.error : "Preparing…"}
                </div>
              </button>
              <button className="icon-btn" aria-label={`Delete ${doc.name}`} onClick={() => remove(doc.id, doc.name)}>
                <Trash2 size={15} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
