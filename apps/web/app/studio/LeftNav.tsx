"use client";
import { useEffect, useState } from "react";
import {
  Bookmark,
  FileText,
  MessageSquare,
  Paperclip,
  Search,
  SquarePen,
  StickyNote,
} from "lucide-react";
import { request } from "../lib";
import type { LucideIcon } from "lucide-react";
import type { LeftTab, StudioApi } from "./useStudio";

const TABS: { id: LeftTab; icon: LucideIcon; label: string }[] = [
  { id: "pages", icon: FileText, label: "Pages" },
  { id: "bookmarks", icon: Bookmark, label: "Bookmarks" },
  { id: "comments", icon: MessageSquare, label: "Comments" },
  { id: "attachments", icon: Paperclip, label: "Attachments" },
  { id: "fields", icon: SquarePen, label: "Fields" },
  { id: "search", icon: Search, label: "Search" },
];

function Pages({ s }: { s: StudioApi }) {
  const count = s.documentInfo?.page_count ?? 0;
  return (
    <div className="sd-pages">
      {Array.from({ length: count }, (_, i) => i + 1).map((n) => {
        const info = s.documentInfo?.pages[n - 1];
        return (
          <button
            key={n}
            className={`sd-thumb${s.page === n ? " active" : ""}`}
            onClick={() => s.setPage(n)}
          >
            <div className="sd-thumb-frame" style={info ? { aspectRatio: `${info.width}/${info.height}` } : undefined}>
              {s.page === n && s.pageImage ? <img src={s.pageImage} alt={`Page ${n}`} /> : <span>{n}</span>}
            </div>
            <small>Page {n}</small>
          </button>
        );
      })}
    </div>
  );
}

function Bookmarks({ s }: { s: StudioApi }) {
  return (
    <div className="sd-list">
      <div className="sd-list-add">
        <input value={s.bookmarkTitle} onChange={(e) => s.setBookmarkTitle(e.target.value)} placeholder="Bookmark this page as…" />
        <button disabled={s.busy || !s.bookmarkTitle} onClick={() => s.applyNavigationOperation({ kind: "bookmark.add", bookmark_title: s.bookmarkTitle, bookmark_level: 1, target_page: s.page })}>Add</button>
      </div>
      {s.bookmarks.map((b) => (
        <div key={`${b.index}-${b.title}`} className="sd-list-row">
          <button style={{ paddingLeft: 8 + b.level * 10 }} onClick={() => s.setPage(b.page)}>
            <b>{b.title}</b><small>Page {b.page}</small>
          </button>
          <button className="sd-del" title="Delete" onClick={() => s.applyNavigationOperation({ kind: "bookmark.delete", bookmark_index: b.index })}>×</button>
        </div>
      ))}
      {!s.bookmarks.length && <p className="sd-empty">No bookmarks yet.</p>}
    </div>
  );
}

function Comments({ s }: { s: StudioApi }) {
  return (
    <div className="sd-list">
      <input className="sd-search" value={s.annotationSearch} onChange={(e) => s.setAnnotationSearch(e.target.value)} placeholder="Search comments" />
      <div className="sd-grid2 sd-list-filters">
        <select value={s.annotationPageFilter} onChange={(e) => s.setAnnotationPageFilter(e.target.value)}>
          <option value="all">All pages</option>
          <option value="current">Current page</option>
        </select>
        <select value={s.annotationSort} onChange={(e) => s.setAnnotationSort(e.target.value)}>
          <option value="page">Page order</option>
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
        </select>
      </div>
      <label className="sd-check"><input type="checkbox" checked={s.hideResolved} onChange={(e) => s.setHideResolved(e.target.checked)} /> Hide resolved</label>
      {s.annotations.map((a) => (
        <button
          key={a.id}
          className={`sd-comment${s.selectedAnnotationId === a.id ? " active" : ""}${a.parent_id ? " reply" : ""}`}
          onClick={() => {
            s.selectObject({ kind: "annotation", id: a.id });
            s.setPage(a.page);
            s.setAnnotationAuthor(a.author);
            s.setAnnotationStatus(a.status);
            s.setColor(a.color);
            s.setText(a.comment);
          }}
        >
          <span className="sd-comment-head"><b>{a.author || "Anonymous"}</b><small>p{a.page} · {a.type} · {a.status}</small></span>
          <span className="sd-comment-body">{a.comment || a.subject || "Annotation"}</span>
          {!!a.reply_count && <small>{a.reply_count} replies</small>}
        </button>
      ))}
      {!s.annotations.length && <p className="sd-empty"><StickyNote /> No comments match.</p>}
    </div>
  );
}

function Attachments({ s }: { s: StudioApi }) {
  return (
    <div className="sd-list">
      <div className="sd-list-add sd-col">
        <select value={s.attachmentAssetId} onChange={(e) => { s.setAttachmentAssetId(e.target.value); const a = s.files.find((f) => f.id === e.target.value); if (a) s.setAttachmentName(a.display_name); }}>
          <option value="">Choose a vault file…</option>
          {s.files.map((f) => <option key={f.id} value={f.id}>{f.display_name}</option>)}
        </select>
        <input value={s.attachmentName} onChange={(e) => s.setAttachmentName(e.target.value)} placeholder="Embedded filename" />
        <button disabled={s.busy || !s.attachmentAssetId || !s.attachmentName} onClick={() => s.applyNavigationOperation({ kind: "attachment.add", attachment_file_id: s.attachmentAssetId, attachment_name: s.attachmentName, text: `Embedded from ${s.attachmentName}` })}>Embed file</button>
      </div>
      {s.embeddedAttachments.map((att) => (
        <div key={att.name} className="sd-list-row">
          <button onClick={() => s.downloadEmbeddedAttachment(att.name)}><b>{att.name}</b><small>{att.size || 0} bytes</small></button>
          <button className="sd-del" title="Delete" onClick={() => s.applyNavigationOperation({ kind: "attachment.delete", attachment_name: att.name })}>×</button>
        </div>
      ))}
      {!s.embeddedAttachments.length && <p className="sd-empty">No embedded files.</p>}
    </div>
  );
}

function Fields({ s }: { s: StudioApi }) {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const sessionId = s.workspaceSession?.id;
  useEffect(() => {
    if (!sessionId) return;
    request<{ items: Record<string, unknown>[] }>(`/api/v1/pdf/sessions/${sessionId}/forms`)
      .then((r) => setItems(r.items || []))
      .catch(() => setItems([]));
  }, [sessionId, s.workspaceSession?.revision]);
  return (
    <div className="sd-list">
      {items.map((field, i) => (
        <button key={i} className="sd-list-row-flat" onClick={() => { const p = Number(field.page); if (p) s.setPage(p); s.setWorkMode("forms"); }}>
          <b>{String(field.name ?? field.field_name ?? `Field ${i + 1}`)}</b>
          <small>{String(field.type ?? field.field_type ?? "field")}{field.page ? ` · p${field.page}` : ""}</small>
        </button>
      ))}
      {!items.length && <p className="sd-empty">No form fields. Add them in Forms mode.</p>}
    </div>
  );
}

function SearchTab({ s }: { s: StudioApi }) {
  const q = s.searchQuery.trim().toLowerCase();
  const textHits = q ? s.sceneText.filter((t) => t.text.toLowerCase().includes(q)) : [];
  const commentHits = q ? s.annotations.filter((a) => (a.comment || "").toLowerCase().includes(q)) : [];
  const bookmarkHits = q ? s.bookmarks.filter((b) => b.title.toLowerCase().includes(q)) : [];
  return (
    <div className="sd-list">
      <input className="sd-search" value={s.searchQuery} onChange={(e) => s.setSearchQuery(e.target.value)} placeholder="Search current page, comments & bookmarks…" autoFocus />
      {!q && <p className="sd-empty">Type to search page text, comments, and bookmarks.</p>}
      {q && (
        <>
          {!!textHits.length && <p className="sd-group">Text on this page ({textHits.length})</p>}
          {textHits.slice(0, 40).map((t) => (
            <button key={t.id} className="sd-list-row-flat" onClick={() => s.selectObject({ kind: "text", object: t })}>
              <span>{t.text}</span>
            </button>
          ))}
          {!!commentHits.length && <p className="sd-group">Comments ({commentHits.length})</p>}
          {commentHits.map((a) => (
            <button key={a.id} className="sd-list-row-flat" onClick={() => { s.setPage(a.page); s.selectObject({ kind: "annotation", id: a.id }); }}>
              <span>{a.comment}</span><small>p{a.page}</small>
            </button>
          ))}
          {!!bookmarkHits.length && <p className="sd-group">Bookmarks ({bookmarkHits.length})</p>}
          {bookmarkHits.map((b) => (
            <button key={`${b.index}-${b.title}`} className="sd-list-row-flat" onClick={() => s.setPage(b.page)}>
              <span>{b.title}</span><small>p{b.page}</small>
            </button>
          ))}
          {!textHits.length && !commentHits.length && !bookmarkHits.length && <p className="sd-empty">No matches on this page or in comments/bookmarks.</p>}
        </>
      )}
    </div>
  );
}

export function LeftNav({ s }: { s: StudioApi }) {
  return (
    <aside className="sd-leftnav">
      <div className="sd-leftnav-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} className={`sd-navtab${s.leftTab === t.id ? " active" : ""}`} title={t.label} onClick={() => s.setLeftTab(t.id)}>
              <Icon />
            </button>
          );
        })}
      </div>
      <div className="sd-leftnav-body">
        <p className="sd-panel-title">{TABS.find((t) => t.id === s.leftTab)?.label}</p>
        {s.leftTab === "pages" && <Pages s={s} />}
        {s.leftTab === "bookmarks" && <Bookmarks s={s} />}
        {s.leftTab === "comments" && <Comments s={s} />}
        {s.leftTab === "attachments" && <Attachments s={s} />}
        {s.leftTab === "fields" && <Fields s={s} />}
        {s.leftTab === "search" && <SearchTab s={s} />}
      </div>
    </aside>
  );
}
