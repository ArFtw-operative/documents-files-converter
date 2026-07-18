"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { MODES } from "./registry";
import type { StudioApi, WorkMode } from "./useStudio";

type Command = { id: string; label: string; hint?: string; run: () => void };

function buildCommands(s: StudioApi): Command[] {
  const commands: Command[] = [];
  MODES.filter((mode) => mode.id !== "ocr" || s.hasCapability("pdf.ocr")).forEach((mode) =>
    commands.push({
      id: `mode-${mode.id}`,
      label: `${mode.label} mode`,
      hint: "Work mode",
      run: () => {
        s.setWorkMode(mode.id as WorkMode);
        s.setTool("select");
      },
    }),
  );
  commands.push(
    { id: "save", label: "Save (new revision)", hint: "Ctrl+S", run: () => s.saveProject() },
    { id: "export", label: "Export PDF", run: () => s.publish() },
    { id: "undo", label: "Undo", hint: "Ctrl+Z", run: () => s.historyAction("undo") },
    { id: "redo", label: "Redo", hint: "Ctrl+Y", run: () => s.historyAction("redo") },
    { id: "edit-text", label: "Edit text in place", hint: "Edit", run: () => { s.setWorkMode("edit"); s.setTool("edit_text"); } },
    { id: "add-text", label: "Add text box", hint: "Edit", run: () => { s.setWorkMode("edit"); s.setTool("text"); } },
    { id: "highlight", label: "Highlight text", hint: "Comment", run: () => { s.setWorkMode("comment"); s.setTool("highlight"); } },
    { id: "compress", label: "Compress PDF", hint: "Job", run: () => s.runJob("pdf.compress", "pdf", { preset: "balanced", remove_metadata: true }) },
    { id: "extract-text", label: "Convert to text", hint: "Job", run: () => s.runJob("pdf.extract_text", "txt", {}) },
    { id: "split", label: "Split every page", hint: "Job", run: () => s.runJob("pdf.split", "zip", { pages: "every" }) },
    { id: "redact", label: "Redact by pattern", hint: "Redact", run: () => s.setWorkMode("redact") },
    { id: "compare", label: "Compare with another PDF", hint: "Compare", run: () => s.setWorkMode("compare") },
    { id: "organize", label: "Organize pages", hint: "Organize", run: () => s.setWorkMode("organize") },
    { id: "theme", label: `Switch to ${s.theme === "dark" ? "light" : "dark"} theme`, run: () => s.setTheme(s.theme === "dark" ? "light" : "dark") },
    { id: "density", label: `Use ${s.density === "compact" ? "comfortable" : "compact"} spacing`, run: () => s.setDensity(s.density === "compact" ? "comfortable" : "compact") },
  );
  if (s.hasCapability("pdf.ocr")) {
    commands.push({ id: "ocr", label: "OCR document (make searchable)", hint: "Job", run: () => s.runJob("pdf.ocr", "pdf", { language: "eng", deskew: true, rotate_pages: true }) });
  }
  return commands;
}

export function CommandPalette({ s }: { s: StudioApi }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const commands = useMemo(() => buildCommands(s), [s]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q) || (c.hint ?? "").toLowerCase().includes(q));
  }, [commands, query]);

  useEffect(() => {
    if (s.paletteOpen) {
      setQuery("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [s.paletteOpen]);

  if (!s.paletteOpen) return null;

  const runAt = (index: number) => {
    const command = filtered[index];
    if (command) {
      command.run();
      s.setPaletteOpen(false);
    }
  };

  return (
    <div className="sd-palette-backdrop" onClick={() => s.setPaletteOpen(false)}>
      <div className="sd-palette" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="sd-palette-input"
          placeholder="Search commands… (compress, OCR, redact, extract pages)"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setActive(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(filtered.length - 1, a + 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
            if (e.key === "Enter") { e.preventDefault(); runAt(active); }
            if (e.key === "Escape") { e.preventDefault(); s.setPaletteOpen(false); }
          }}
        />
        <div className="sd-palette-list">
          {filtered.map((command, index) => (
            <button
              key={command.id}
              className={`sd-palette-item${index === active ? " active" : ""}`}
              onMouseEnter={() => setActive(index)}
              onClick={() => runAt(index)}
            >
              <span>{command.label}</span>
              {command.hint && <small>{command.hint}</small>}
            </button>
          ))}
          {!filtered.length && <div className="sd-palette-empty">No matching commands.</div>}
        </div>
      </div>
    </div>
  );
}
