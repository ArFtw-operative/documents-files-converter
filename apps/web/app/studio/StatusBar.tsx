"use client";
import { ChevronLeft, ChevronRight, Maximize2, ZoomIn, ZoomOut } from "lucide-react";
import type { StudioApi } from "./useStudio";

export function StatusBar({ s }: { s: StudioApi }) {
  const count = s.documentInfo?.page_count ?? 0;
  return (
    <div className="sd-statusbar">
      <div className="sd-status-left">
        <button disabled={s.page <= 1} onClick={() => s.setPage(Math.max(1, s.page - 1))} title="Previous page"><ChevronLeft /></button>
        <span className="sd-pagebox">
          <input
            type="number"
            min={1}
            max={count || 1}
            value={s.page}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (n >= 1 && n <= count) s.setPage(n);
            }}
          />
          <small>of {count}</small>
        </span>
        <button disabled={s.page >= count} onClick={() => s.setPage(Math.min(count, s.page + 1))} title="Next page"><ChevronRight /></button>
      </div>

      <div className="sd-status-mid">
        {s.pageInfo && (
          <small>{Math.round(s.pageInfo.width)} × {Math.round(s.pageInfo.height)} pt · {s.workMode} mode</small>
        )}
      </div>

      <div className="sd-status-right">
        <button onClick={() => s.setZoom(Math.max(0.4, Math.round((s.zoom - 0.1) * 10) / 10))} title="Zoom out"><ZoomOut /></button>
        <button className="sd-zoom-value" onClick={() => s.setZoom(1)} title="Reset zoom">{Math.round(s.zoom * 100)}%</button>
        <button onClick={() => s.setZoom(Math.min(4, Math.round((s.zoom + 0.1) * 10) / 10))} title="Zoom in"><ZoomIn /></button>
        <button onClick={s.fitWidth} title="Fit width"><Maximize2 /></button>
      </div>
    </div>
  );
}
