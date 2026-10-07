import { memo, useEffect, useRef, useState } from "react";
import * as Menu from "@radix-ui/react-dropdown-menu";
import type { PDFDocumentProxy } from "pdfjs-dist";
import type { PageInfo } from "@folio/scene-schema";
import { ArrowDown, ArrowUp, FilePlus2, MoreVertical, RotateCcw, RotateCw, Trash2 } from "lucide-react";
import { useViewport } from "../stores";
import type { useEditActions } from "../useEditActions";
import { displaySize } from "../canvas/DocumentCanvas";

const WIDTH = 132;

const Thumbnail = memo(function Thumbnail({ pdf, page, revision }: { pdf: PDFDocumentProxy; page: PageInfo; revision: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const holder = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const { w, h } = displaySize(page);
  const height = Math.round((WIDTH * h) / w);

  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "300px" });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || !canvas.current) return;
    let task: ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]> | null = null;
    let alive = true;
    pdf.getPage(page.index + 1).then((p) => {
      if (!alive || !canvas.current) return;
      const viewport = p.getViewport({ scale: (WIDTH * 2) / p.getViewport({ scale: 1 }).width });
      canvas.current.width = viewport.width;
      canvas.current.height = viewport.height;
      task = p.render({ canvas: canvas.current, viewport });
      task.promise.catch(() => undefined);
    }).catch(() => undefined);
    return () => {
      alive = false;
      task?.cancel();
    };
  }, [visible, pdf, page.index, revision, page.version]);

  return (
    <div ref={holder} className="bg-white page-shadow" style={{ width: WIDTH, height }}>
      <canvas ref={canvas} style={{ width: WIDTH, height }} aria-hidden />
    </div>
  );
});

export function ThumbnailRail({ pdf, pages, revision, actions }: {
  pdf: PDFDocumentProxy; pages: PageInfo[]; revision: number; actions: ReturnType<typeof useEditActions>;
}) {
  const current = useViewport((s) => s.currentPage);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    list.current?.querySelector(`[data-thumb="${current}"]`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  return (
    <aside className="chrome border-r w-[200px] shrink-0 flex flex-col min-h-0" aria-label="Pages">
      <div className="px-3 py-2 text-xs font-semibold muted uppercase tracking-wide">Pages</div>
      <div ref={list} className="flex-1 overflow-y-auto px-3 pb-4 space-y-3">
        {pages.map((page) => (
          <div key={page.page_id} data-thumb={page.index} className="group relative flex flex-col items-center">
            <button
              className={`rounded-sm p-0.5 ${current === page.index ? "ring-2 ring-[var(--color-select)]" : "hover:ring-1 hover:ring-[var(--chrome-border)]"}`}
              onClick={() => useViewport.getState().requestScroll(page.index)}
              aria-label={`Go to page ${page.index + 1}`}
              aria-current={current === page.index ? "page" : undefined}
            >
              <Thumbnail pdf={pdf} page={page} revision={revision} />
            </button>
            <div className="flex items-center gap-1 mt-1 text-xs muted">
              <span className="tabular-nums">{page.index + 1}</span>
              <Menu.Root>
                <Menu.Trigger asChild>
                  <button className="icon-btn !size-6 opacity-60 group-hover:opacity-100" aria-label={`Page ${page.index + 1} actions`}>
                    <MoreVertical size={13} aria-hidden />
                  </button>
                </Menu.Trigger>
                <Menu.Portal>
                  <Menu.Content className="menu" sideOffset={4} align="start">
                    <Menu.Item className="menu-item" onSelect={() => actions.pageOperation("rotate_page", page.page_id, { degrees: 90 })}>
                      <RotateCw size={14} aria-hidden /> Rotate right
                    </Menu.Item>
                    <Menu.Item className="menu-item" onSelect={() => actions.pageOperation("rotate_page", page.page_id, { degrees: 270 })}>
                      <RotateCcw size={14} aria-hidden /> Rotate left
                    </Menu.Item>
                    <Menu.Separator className="menu-separator" />
                    <Menu.Item className="menu-item" disabled={page.index === 0}
                      onSelect={() => actions.pageOperation("reorder_page", page.page_id, { to: page.index - 1 })}>
                      <ArrowUp size={14} aria-hidden /> Move up
                    </Menu.Item>
                    <Menu.Item className="menu-item" disabled={page.index === pages.length - 1}
                      onSelect={() => actions.pageOperation("reorder_page", page.page_id, { to: page.index + 1 })}>
                      <ArrowDown size={14} aria-hidden /> Move down
                    </Menu.Item>
                    <Menu.Item className="menu-item" onSelect={() => actions.pageOperation("insert_page", null, { at: page.index + 1 })}>
                      <FilePlus2 size={14} aria-hidden /> Insert blank page after
                    </Menu.Item>
                    <Menu.Separator className="menu-separator" />
                    <Menu.Item className="menu-item btn-danger" disabled={pages.length === 1}
                      onSelect={() => window.confirm(`Delete page ${page.index + 1}? You can undo this.`) &&
                        actions.pageOperation("delete_page", page.page_id)}>
                      <Trash2 size={14} aria-hidden /> Delete page
                    </Menu.Item>
                  </Menu.Content>
                </Menu.Portal>
              </Menu.Root>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
