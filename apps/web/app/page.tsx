"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  Download,
  Eraser,
  Eye,
  FileText,
  FolderOpen,
  Highlighter,
  History,
  Link2,
  LogOut,
  MessageSquare,
  MousePointer2,
  PenTool,
  Plus,
  RefreshCw,
  Redo2,
  RotateCcw,
  RotateCw,
  Save,
  Search,
  Settings,
  ShieldCheck,
  Square,
  Star,
  Tag as TagIcon,
  Trash2,
  Type,
  Undo2,
  UploadCloud,
  Users,
  WandSparkles,
  XCircle,
} from "lucide-react";
import { API, request, size } from "./lib";
import type {
  Capability,
  Engine,
  Folder,
  Job,
  SavedPreset,
  Tag,
  User,
  VaultFile,
} from "./types";
import { StudioShell } from "./studio/StudioShell";

export default function Home() {
  const [boot, setBoot] = useState(true),
    [setup, setSetup] = useState(false),
    [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    request<{ required: boolean }>("/api/v1/setup/status")
      .then(async (s) => {
        setSetup(s.required);
        if (!s.required && localStorage.getItem("access_token"))
          setUser(await request<User>("/api/v1/auth/me"));
      })
      .catch(() => {})
      .finally(() => setBoot(false));
  }, []);
  if (boot)
    return (
      <main className="center">
        <div className="loader" />
        <p>Opening your private vault…</p>
      </main>
    );
  if (!user)
    return (
      <Auth
        setup={setup}
        onAuthenticated={(u) => {
          setUser(u);
          setSetup(false);
        }}
      />
    );
  return (
    <Vault
      user={user}
      onLogout={() => {
        const refreshToken = localStorage.getItem("refresh_token");
        const finish = () => {
          localStorage.clear();
          setUser(null);
        };
        if (refreshToken)
          request("/api/v1/auth/logout", {
            method: "POST",
            body: JSON.stringify({ refresh_token: refreshToken }),
          }).finally(finish);
        else finish();
      }}
    />
  );
}

function Auth({
  setup,
  onAuthenticated,
}: {
  setup: boolean;
  onAuthenticated: (user: User) => void;
}) {
  const [email, setEmail] = useState(""),
    [name, setName] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = setup
        ? { email, display_name: name, password }
        : { email, password };
      const data = await request<{
        access_token: string;
        refresh_token: string;
        user: User;
      }>(setup ? "/api/v1/setup" : "/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(body),
      });
      localStorage.setItem("access_token", data.access_token);
      localStorage.setItem("refresh_token", data.refresh_token);
      onAuthenticated(data.user);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to continue");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-shell">
      <section className="brand-panel">
        <div className="mark">
          <Archive />
        </div>
        <h1>ConvertVault</h1>
        <p>
          Your files stay yours. Convert, organize, and retrieve documents on
          infrastructure you control.
        </p>
        <div className="trust">
          <ShieldCheck /> Local processing · Private storage · No cloud
          conversion
        </div>
      </section>
      <section className="auth-card">
        <p className="eyebrow">{setup ? "FIRST-TIME SETUP" : "WELCOME BACK"}</p>
        <h2>
          {setup
            ? "Create your administrator account"
            : "Sign in to your vault"}
        </h2>
        <p className="muted">
          {setup
            ? "This account will manage users, engines, and system settings."
            : "Continue to your private document workspace."}
        </p>
        <form onSubmit={submit}>
          {setup && (
            <label>
              Your name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
          )}
          <label>
            Email address
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={setup ? 12 : 1}
              required
            />
          </label>
          {error && (
            <div className="error">
              <XCircle /> {error}
            </div>
          )}
          <button className="primary" disabled={busy}>
            {busy ? "Please wait…" : setup ? "Create administrator" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function Vault({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [files, setFiles] = useState<VaultFile[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [caps, setCaps] = useState<Capability[]>([]),
    [savedPresets, setSavedPresets] = useState<SavedPreset[]>([]),
    [presetName, setPresetName] = useState(""),
    [tab, setTab] = useState("convert"),
    [search, setSearch] = useState(""),
    [selected, setSelected] = useState<VaultFile | null>(null),
    [operation, setOperation] = useState(""),
    [target, setTarget] = useState(""),
    [quality, setQuality] = useState(85),
    [targetSizeKb, setTargetSizeKb] = useState(0),
    [gifDuration, setGifDuration] = useState(250),
    [pages, setPages] = useState("1"),
    [dpi, setDpi] = useState(144),
    [rotation, setRotation] = useState(90),
    [pdfPassword, setPdfPassword] = useState(""),
    [preset, setPreset] = useState("balanced"),
    [imageFormat, setImageFormat] = useState("png"),
    [language, setLanguage] = useState("eng"),
    [pageStart, setPageStart] = useState(1),
    [pagePosition, setPagePosition] = useState("bottom-center"),
    [inputIds, setInputIds] = useState<string[]>([]),
    [notice, setNotice] = useState(""),
    [loading, setLoading] = useState(true);
  const input = useRef<HTMLInputElement>(null);
  const load = async () => {
    try {
      const [f, j, c, p] = await Promise.all([
        request<{ items: VaultFile[] }>(
          `/api/v1/files?search=${encodeURIComponent(search)}`,
        ),
        request<{ items: Job[] }>("/api/v1/jobs"),
        request<{ items: Capability[] }>("/api/v1/capabilities"),
        request<{ items: SavedPreset[] }>("/api/v1/presets"),
      ]);
      setFiles(f.items);
      setJobs(j.items);
      setCaps(c.items);
      setSavedPresets(p.items);
      setNotice("");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not refresh");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [search]);
  const available = useMemo(
    () =>
      selected
        ? caps.filter((c) =>
            c.source_extensions.includes(selected.extension.toLowerCase()),
          )
        : [],
    [caps, selected],
  );
  useEffect(() => {
    const first = available[0];
    setOperation(first?.operation || "");
    setTarget(first?.target_extensions[0] || "");
    setInputIds(selected ? [selected.id] : []);
  }, [selected, available.length]);
  async function upload(list: FileList | null) {
    if (!list) return;
    for (const file of Array.from(list)) {
      const form = new FormData();
      form.append("file", file);
      try {
        await request("/api/v1/files", { method: "POST", body: form });
        setNotice(`${file.name} uploaded securely.`);
      } catch (e) {
        setNotice(e instanceof Error ? e.message : "Upload failed");
      }
    }
    await load();
  }
  function currentOptions() {
    const options: Record<string, unknown> = {};
    if (["image.convert", "image.compress"].includes(operation))
      Object.assign(options, { quality, auto_orient: true });
    if (operation === "image.compress")
      Object.assign(options, {
        preset,
        target_size_kb: targetSizeKb || undefined,
      });
    if (operation === "image.extract_frames") options.format = imageFormat;
    if (operation === "image.create_gif")
      Object.assign(options, { duration_ms: gifDuration, loop: 0 });
    if (["pdf.extract_pages", "pdf.rotate"].includes(operation))
      options.pages = pages;
    if (operation === "pdf.rotate") options.rotate = rotation;
    if (operation === "pdf.render")
      Object.assign(options, { page: Number(pages) || 1, dpi });
    if (operation === "pdf.render_all")
      Object.assign(options, { format: imageFormat, dpi });
    if (operation === "pdf.split") options.pages = pages.trim() || "every";
    if (operation === "pdf.compress")
      Object.assign(options, { preset, remove_metadata: true });
    if (operation === "pdf.ocr")
      Object.assign(options, { language, deskew: true, rotate_pages: true });
    if (operation === "text.extract")
      Object.assign(options, {
        ocr_language: language,
        normalize_whitespace: true,
        reflow_paragraphs: true,
      });
    if (operation === "pdf.page_numbers")
      Object.assign(options, { start: pageStart, position: pagePosition });
    return options;
  }
  async function convert() {
    if (!selected || !operation || !target) return;
    const options = currentOptions();
    if (["pdf.encrypt", "pdf.decrypt"].includes(operation))
      options.password = pdfPassword;
    try {
      await request("/api/v1/jobs", {
        method: "POST",
        body: JSON.stringify({
          input_file_id: selected.id,
          input_file_ids: [
            "pdf.merge",
            "image.to_pdf",
            "image.create_gif",
          ].includes(operation)
            ? inputIds
            : [],
          operation,
          target_format: target,
          options,
        }),
      });
      setPdfPassword("");
      setNotice("Conversion queued. You can keep working while it runs.");
      setTab("jobs");
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Could not start conversion");
    }
  }
  async function savePreset() {
    if (!presetName.trim()) return;
    try {
      await request("/api/v1/presets", {
        method: "POST",
        body: JSON.stringify({
          name: presetName.trim(),
          operation,
          target_format: target,
          options: currentOptions(),
        }),
      });
      setPresetName("");
      setNotice("Preset saved for future conversions.");
      await load();
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Preset could not be saved",
      );
    }
  }
  function applyPreset(saved: SavedPreset) {
    setOperation(saved.operation);
    setTarget(saved.target_format);
    const options = saved.options;
    if (typeof options.quality === "number") setQuality(options.quality);
    if (typeof options.target_size_kb === "number")
      setTargetSizeKb(options.target_size_kb);
    if (typeof options.duration_ms === "number")
      setGifDuration(options.duration_ms);
    if (typeof options.pages === "string") setPages(options.pages);
    if (typeof options.page === "number") setPages(String(options.page));
    if (typeof options.dpi === "number") setDpi(options.dpi);
    if (typeof options.rotate === "number") setRotation(options.rotate);
    if (typeof options.preset === "string") setPreset(options.preset);
    if (typeof options.format === "string") setImageFormat(options.format);
    if (typeof options.language === "string") setLanguage(options.language);
    if (typeof options.start === "number") setPageStart(options.start);
    if (typeof options.position === "string") setPagePosition(options.position);
    setNotice(`Preset “${saved.name}” applied.`);
  }
  async function trash(file: VaultFile) {
    await request(`/api/v1/files/${file.id}/trash`, { method: "POST" });
    if (selected?.id === file.id) setSelected(null);
    await load();
  }
  return (
    <div className="app">
      <aside>
        <div className="logo">
          <span>
            <Archive />
          </span>
          <b>ConvertVault</b>
        </div>
        <nav>
          <button
            className={tab === "convert" ? "active" : ""}
            onClick={() => setTab("convert")}
          >
            <WandSparkles /> Convert
          </button>
          <button
            className={tab === "library" ? "active" : ""}
            onClick={() => setTab("library")}
          >
            <FolderOpen /> Library <small>{files.length}</small>
          </button>
          <button
            className={tab === "editor" ? "active" : ""}
            onClick={() => setTab("editor")}
          >
            <PenTool /> PDF Studio
          </button>
          <button
            className={tab === "jobs" ? "active" : ""}
            onClick={() => setTab("jobs")}
          >
            <History /> Jobs{" "}
            <small>
              {
                jobs.filter((j) => ["queued", "running"].includes(j.status))
                  .length
              }
            </small>
          </button>
          {user.role === "admin" && (
            <button
              className={tab === "admin" ? "active" : ""}
              onClick={() => setTab("admin")}
            >
              <Settings /> Admin
            </button>
          )}
        </nav>
        <div className="profile">
          <div className="avatar">{user.display_name[0]?.toUpperCase()}</div>
          <div>
            <b>{user.display_name}</b>
            <small>{user.role}</small>
          </div>
          <button title="Sign out" onClick={onLogout}>
            <LogOut />
          </button>
        </div>
      </aside>
      <main className="workspace">
        <header>
          <div>
            <p className="eyebrow">PRIVATE WORKSPACE</p>
            <h1>
              {tab === "convert"
                ? "Convert files"
                : tab === "library"
                  ? "Your library"
                  : tab === "editor"
                    ? "PDF Studio"
                    : tab === "jobs"
                      ? "Conversion jobs"
                      : "Administration"}
            </h1>
          </div>
          {tab !== "admin" && (
            <div className="search">
              <Search />
              <input
                aria-label="Search files"
                placeholder="Search your vault"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          )}
        </header>
        {notice && (
          <div className="notice" onClick={() => setNotice("")}>
            {notice}
          </div>
        )}
        {tab === "convert" && (
          <section className="convert-layout">
            <div>
              <div
                className="dropzone"
                tabIndex={0}
                onClick={() => input.current?.click()}
                onKeyDown={(e) => e.key === "Enter" && input.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  upload(e.dataTransfer.files);
                }}
              >
                <input
                  ref={input}
                  type="file"
                  multiple
                  hidden
                  onChange={(e) => upload(e.target.files)}
                />
                <UploadCloud />
                <h2>Drop files here to begin</h2>
                <p>or choose files from your device</p>
                <button className="secondary">Choose files</button>
                <small>Files are processed entirely on this server</small>
              </div>
              <h3 className="section-title">Recent files</h3>
              <FileGrid
                files={files.slice(0, 6)}
                selected={selected}
                onSelect={setSelected}
                onTrash={trash}
              />
            </div>
            <aside className="conversion-card">
              <p className="eyebrow">CONVERSION SETTINGS</p>
              {selected ? (
                <>
                  <div className="selected-file">
                    <FileText />
                    <div>
                      <b>{selected.display_name}</b>
                      <small>
                        {size(selected.size)} ·{" "}
                        {selected.extension.toUpperCase()}
                      </small>
                    </div>
                  </div>
                  <SecurePreview file={selected} />
                  {available.length ? (
                    <>
                      <label>
                        Operation
                        <select
                          value={operation}
                          onChange={(e) => {
                            setOperation(e.target.value);
                            setPreset("balanced");
                            const c = available.find(
                              (x) => x.operation === e.target.value,
                            );
                            setTarget(c?.target_extensions[0] || "");
                          }}
                        >
                          {available.map((c) => (
                            <option
                              key={`${c.engine_id}-${c.operation}`}
                              value={c.operation}
                            >
                              {c.operation.replaceAll(".", " ")}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Output format
                        <select
                          value={target}
                          onChange={(e) => setTarget(e.target.value)}
                        >
                          {available
                            .find((c) => c.operation === operation)
                            ?.target_extensions.map((t) => (
                              <option key={t}>{t}</option>
                            ))}
                        </select>
                      </label>
                      {["image.convert", "image.compress"].includes(
                        operation,
                      ) && (
                        <label>
                          Quality <span>{quality}%</span>
                          <input
                            type="range"
                            min="1"
                            max="100"
                            value={quality}
                            onChange={(e) => setQuality(+e.target.value)}
                          />
                        </label>
                      )}
                      {operation === "image.compress" && (
                        <>
                          <label>
                            Compression preset
                            <select
                              value={preset}
                              onChange={(e) => setPreset(e.target.value)}
                            >
                              <option value="lossless">Lossless</option>
                              <option value="balanced">Balanced</option>
                              <option value="maximum">
                                Maximum compression
                              </option>
                              <option value="custom">Custom</option>
                            </select>
                          </label>
                          <label>
                            Target size in KB (optional)
                            <input
                              type="number"
                              min="0"
                              value={targetSizeKb}
                              onChange={(e) => setTargetSizeKb(+e.target.value)}
                            />
                          </label>
                        </>
                      )}
                      {operation === "image.extract_frames" && (
                        <label>
                          Frame format
                          <select
                            value={imageFormat}
                            onChange={(e) => setImageFormat(e.target.value)}
                          >
                            <option value="png">PNG</option>
                            <option value="jpg">JPEG</option>
                          </select>
                        </label>
                      )}
                      {operation === "image.create_gif" && (
                        <label>
                          Frame duration <span>{gifDuration} ms</span>
                          <input
                            type="range"
                            min="20"
                            max="2000"
                            step="10"
                            value={gifDuration}
                            onChange={(e) => setGifDuration(+e.target.value)}
                          />
                        </label>
                      )}
                      {[
                        "pdf.extract_pages",
                        "pdf.rotate",
                        "pdf.render",
                      ].includes(operation) && (
                        <label>
                          {operation === "pdf.render"
                            ? "Page number"
                            : "Pages (for example 1-3,5)"}
                          <input
                            value={pages}
                            onChange={(e) => setPages(e.target.value)}
                          />
                        </label>
                      )}
                      {operation === "pdf.split" && (
                        <label>
                          Pages or “every”
                          <input
                            value={pages}
                            onChange={(e) => setPages(e.target.value)}
                            placeholder="every"
                          />
                        </label>
                      )}
                      {operation === "pdf.rotate" && (
                        <label>
                          Rotation
                          <select
                            value={rotation}
                            onChange={(e) => setRotation(+e.target.value)}
                          >
                            <option value={90}>90°</option>
                            <option value={180}>180°</option>
                            <option value={270}>270°</option>
                          </select>
                        </label>
                      )}
                      {["pdf.render", "pdf.render_all"].includes(operation) && (
                        <label>
                          Resolution <span>{dpi} DPI</span>
                          <input
                            type="range"
                            min="72"
                            max="300"
                            step="24"
                            value={dpi}
                            onChange={(e) => setDpi(+e.target.value)}
                          />
                        </label>
                      )}
                      {operation === "pdf.render_all" && (
                        <label>
                          Image format
                          <select
                            value={imageFormat}
                            onChange={(e) => setImageFormat(e.target.value)}
                          >
                            <option value="png">PNG</option>
                            <option value="jpg">JPEG</option>
                          </select>
                        </label>
                      )}
                      {operation === "pdf.compress" && (
                        <label>
                          Compression preset
                          <select
                            value={preset}
                            onChange={(e) => setPreset(e.target.value)}
                          >
                            <option value="archival">Archival</option>
                            <option value="print">Print</option>
                            <option value="balanced">Balanced</option>
                            <option value="screen">Screen</option>
                            <option value="maximum">Maximum</option>
                          </select>
                        </label>
                      )}
                      {["pdf.encrypt", "pdf.decrypt"].includes(operation) && (
                        <label>
                          Document password
                          <input
                            type="password"
                            value={pdfPassword}
                            onChange={(e) => setPdfPassword(e.target.value)}
                            minLength={operation === "pdf.encrypt" ? 8 : 1}
                            autoComplete="new-password"
                          />
                        </label>
                      )}
                      {["pdf.ocr", "text.extract"].includes(operation) && (
                        <label>
                          {operation === "text.extract"
                            ? "Extraction/OCR language"
                            : "OCR language"}
                          <input
                            value={language}
                            onChange={(e) => setLanguage(e.target.value)}
                            placeholder="eng"
                          />
                        </label>
                      )}
                      {operation === "pdf.page_numbers" && (
                        <>
                          <label>
                            First page number
                            <input
                              type="number"
                              value={pageStart}
                              onChange={(e) => setPageStart(+e.target.value)}
                            />
                          </label>
                          <label>
                            Position
                            <select
                              value={pagePosition}
                              onChange={(e) => setPagePosition(e.target.value)}
                            >
                              <option value="bottom-center">
                                Bottom center
                              </option>
                              <option value="bottom-right">Bottom right</option>
                              <option value="top-right">Top right</option>
                            </select>
                          </label>
                        </>
                      )}
                      {[
                        "pdf.merge",
                        "image.to_pdf",
                        "image.create_gif",
                      ].includes(operation) && (
                        <div className="batch-inputs">
                          <b>
                            {operation === "pdf.merge"
                              ? "PDFs to merge, in library order"
                              : operation === "image.to_pdf"
                                ? "Images to include as PDF pages"
                                : "Images to include as GIF frames"}
                          </b>
                          {files
                            .filter((f) =>
                              operation === "pdf.merge"
                                ? f.extension === "pdf"
                                : f.category === "image",
                            )
                            .map((file) => (
                              <label key={file.id}>
                                <input
                                  type="checkbox"
                                  checked={inputIds.includes(file.id)}
                                  onChange={(e) =>
                                    setInputIds((ids) =>
                                      e.target.checked
                                        ? [...new Set([...ids, file.id])]
                                        : ids.filter((id) => id !== file.id),
                                    )
                                  }
                                />
                                <span>{file.display_name}</span>
                              </label>
                            ))}
                        </div>
                      )}
                      <div className="preset-controls">
                        {savedPresets.some((saved) =>
                          available.some(
                            (capability) =>
                              capability.operation === saved.operation,
                          ),
                        ) && (
                          <label>
                            Saved preset
                            <select
                              value=""
                              onChange={(event) => {
                                const saved = savedPresets.find(
                                  (item) => item.id === event.target.value,
                                );
                                if (saved) applyPreset(saved);
                              }}
                            >
                              <option value="">Choose a preset</option>
                              {savedPresets
                                .filter((saved) =>
                                  available.some(
                                    (capability) =>
                                      capability.operation === saved.operation,
                                  ),
                                )
                                .map((saved) => (
                                  <option key={saved.id} value={saved.id}>
                                    {saved.name}
                                  </option>
                                ))}
                            </select>
                          </label>
                        )}
                        <div>
                          <input
                            aria-label="Preset name"
                            value={presetName}
                            onChange={(event) =>
                              setPresetName(event.target.value)
                            }
                            placeholder="Preset name"
                          />
                          <button
                            className="secondary"
                            type="button"
                            onClick={savePreset}
                            disabled={!presetName.trim()}
                          >
                            Save preset
                          </button>
                        </div>
                      </div>
                      <button
                        className="primary"
                        onClick={convert}
                        disabled={
                          ["pdf.merge", "image.create_gif"].includes(
                            operation,
                          ) && inputIds.length < 2
                        }
                      >
                        <WandSparkles /> Start conversion
                      </button>
                      {available
                        .find((c) => c.operation === operation)
                        ?.limitations.map((l) => (
                          <p className="warning" key={l}>
                            {l}
                          </p>
                        ))}
                    </>
                  ) : (
                    <div className="empty small">
                      No installed engine supports this file format.
                    </div>
                  )}
                </>
              ) : (
                <div className="empty">
                  <WandSparkles />
                  <h3>Select a file</h3>
                  <p>Choose a recent file to see compatible conversions.</p>
                </div>
              )}
            </aside>
          </section>
        )}
        {tab === "library" && <LibraryView search={search} onChanged={load} />}{" "}
        {tab === "editor" && <StudioShell files={files} capabilities={caps} onJobsChanged={load} />}{" "}
        {tab === "jobs" && <JobList jobs={jobs} />}{" "}
        {tab === "admin" && user.role === "admin" && <AdminView />}
      </main>
    </div>
  );
}


function FileGrid({
  files,
  selected,
  onSelect,
  onTrash,
}: {
  files: VaultFile[];
  selected: VaultFile | null;
  onSelect: (f: VaultFile) => void;
  onTrash: (f: VaultFile) => void;
}) {
  if (!files.length)
    return (
      <div className="empty">
        <FolderOpen />
        <h3>Your vault is ready</h3>
        <p>Upload a file to begin building your private library.</p>
      </div>
    );
  return (
    <div className="file-grid">
      {files.map((file) => (
        <article
          key={file.id}
          className={selected?.id === file.id ? "selected" : ""}
          onClick={() => onSelect(file)}
        >
          <div className={`file-icon ${file.category}`}>
            <FileText />
            <span>{file.extension}</span>
          </div>
          <h4 title={file.display_name}>{file.display_name}</h4>
          <p>
            {size(file.size)} · {new Date(file.created_at).toLocaleDateString()}
          </p>
          {typeof file.meta.reduction_percent === "number" && (
            <small className="reduction">
              {file.meta.reduction_percent}% smaller
            </small>
          )}
          <div className="file-actions">
            <a
              href={`${API}/api/v1/files/${file.id}/download`}
              onClick={(e) => {
                e.preventDefault();
                fetch(e.currentTarget.href, {
                  headers: {
                    Authorization: `Bearer ${localStorage.getItem("access_token")}`,
                  },
                })
                  .then((r) => r.blob())
                  .then((b) => {
                    const a = document.createElement("a");
                    a.href = URL.createObjectURL(b);
                    a.download = file.display_name;
                    a.click();
                    URL.revokeObjectURL(a.href);
                  });
              }}
              title="Download"
            >
              <Download />
            </a>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onTrash(file);
              }}
              title="Move to trash"
            >
              <Trash2 />
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function LibraryView({
  search,
  onChanged,
}: {
  search: string;
  onChanged: () => void;
}) {
  const [items, setItems] = useState<VaultFile[]>([]),
    [folders, setFolders] = useState<Folder[]>([]),
    [tags, setTags] = useState<Tag[]>([]),
    [selected, setSelected] = useState<VaultFile | null>(null),
    [versions, setVersions] = useState<VaultFile[]>([]),
    [status, setStatus] = useState("active"),
    [category, setCategory] = useState(""),
    [favorites, setFavorites] = useState(false),
    [folderName, setFolderName] = useState(""),
    [tagName, setTagName] = useState(""),
    [message, setMessage] = useState("");
  const loadLibrary = async () => {
    try {
      const query = new URLSearchParams({ search, status });
      if (category) query.set("category", category);
      if (favorites) query.set("favorite", "true");
      const [fileData, folderData, tagData] = await Promise.all([
        request<{ items: VaultFile[] }>(`/api/v1/files?${query}`),
        request<{ items: Folder[] }>("/api/v1/folders"),
        request<{ items: Tag[] }>("/api/v1/tags"),
      ]);
      setItems(fileData.items);
      setFolders(folderData.items);
      setTags(tagData.items);
      if (selected) {
        const fresh = fileData.items.find((file) => file.id === selected.id);
        setSelected(fresh || null);
      }
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Library could not be loaded",
      );
    }
  };
  useEffect(() => {
    loadLibrary();
  }, [search, status, category, favorites]);
  useEffect(() => {
    if (selected)
      request<{ items: VaultFile[] }>(
        `/api/v1/files/${selected.id}/versions`,
      ).then((data) => setVersions(data.items));
    else setVersions([]);
  }, [selected?.id]);
  const change = async (action: () => Promise<unknown>, success: string) => {
    try {
      await action();
      setMessage(success);
      await loadLibrary();
      onChanged();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Action failed");
    }
  };
  const moveTrash = (file: VaultFile) =>
    change(
      () => request(`/api/v1/files/${file.id}/trash`, { method: "POST" }),
      "Moved to Trash.",
    );
  return (
    <section>
      {message && (
        <div className="notice" onClick={() => setMessage("")}>
          {message}
        </div>
      )}
      <div className="library-toolbar">
        <div>
          <button
            className={status === "active" ? "active" : ""}
            onClick={() => setStatus("active")}
          >
            <FolderOpen /> Files
          </button>
          <button
            className={status === "deleted" ? "active" : ""}
            onClick={() => setStatus("deleted")}
          >
            <Trash2 /> Trash
          </button>
        </div>
        <select
          aria-label="Filter by category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">All categories</option>
          <option value="image">Images</option>
          <option value="pdf">PDFs</option>
          <option value="document">Documents</option>
          <option value="spreadsheet">Spreadsheets</option>
          <option value="presentation">Presentations</option>
        </select>
        <label className="favorite-filter">
          <input
            type="checkbox"
            checked={favorites}
            onChange={(e) => setFavorites(e.target.checked)}
          />
          <Star /> Favorites
        </label>
        <button onClick={loadLibrary}>
          <RefreshCw /> Refresh
        </button>
      </div>
      <div className="library-layout">
        <div>
          {status === "active" ? (
            <FileGrid
              files={items}
              selected={selected}
              onSelect={setSelected}
              onTrash={moveTrash}
            />
          ) : (
            <div className="trash-list">
              {items.length === 0 ? (
                <div className="empty">
                  <Trash2 />
                  <h3>Trash is empty</h3>
                </div>
              ) : (
                items.map((file) => (
                  <article key={file.id}>
                    <FileText />
                    <div>
                      <b>{file.display_name}</b>
                      <small>{size(file.size)}</small>
                    </div>
                    <button
                      onClick={() =>
                        change(
                          () =>
                            request(`/api/v1/files/${file.id}/restore`, {
                              method: "POST",
                            }),
                          "File restored.",
                        )
                      }
                    >
                      <RotateCcw /> Restore
                    </button>
                    <button
                      className="danger"
                      onClick={() => {
                        if (
                          confirm(
                            "Permanently delete this file? This cannot be undone.",
                          )
                        )
                          change(
                            () =>
                              request(`/api/v1/files/${file.id}`, {
                                method: "DELETE",
                              }),
                            "File permanently deleted.",
                          );
                      }}
                    >
                      <Trash2 /> Delete forever
                    </button>
                  </article>
                ))
              )}
            </div>
          )}
        </div>
        <aside className="details-panel">
          {selected ? (
            <>
              <p className="eyebrow">FILE DETAILS</p>
              <h3>{selected.display_name}</h3>
              <SecurePreview file={selected} />
              <dl>
                <div>
                  <dt>Size</dt>
                  <dd>{size(selected.size)}</dd>
                </div>
                <div>
                  <dt>Format</dt>
                  <dd>{selected.extension.toUpperCase()}</dd>
                </div>
                <div>
                  <dt>SHA-256</dt>
                  <dd title={selected.checksum_sha256}>
                    {selected.checksum_sha256.slice(0, 12)}…
                  </dd>
                </div>
              </dl>
              <button
                className="secondary"
                onClick={() =>
                  change(
                    () =>
                      request(`/api/v1/files/${selected.id}/favorite`, {
                        method: "POST",
                      }),
                    selected.is_favorite
                      ? "Removed from favorites."
                      : "Added to favorites.",
                  )
                }
              >
                <Star fill={selected.is_favorite ? "currentColor" : "none"} />{" "}
                {selected.is_favorite ? "Unfavorite" : "Favorite"}
              </button>
              <label>
                Folder
                <select
                  value={selected.folder_id || ""}
                  onChange={(e) =>
                    change(
                      () =>
                        request(`/api/v1/files/${selected.id}`, {
                          method: "PATCH",
                          body: JSON.stringify({
                            folder_id: e.target.value || null,
                          }),
                        }),
                      "File moved.",
                    )
                  }
                >
                  <option value="">No folder</option>
                  {folders.map((folder) => (
                    <option key={folder.id} value={folder.id}>
                      {folder.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Add tag
                <select
                  value=""
                  onChange={(e) =>
                    e.target.value &&
                    change(
                      () =>
                        request(
                          `/api/v1/files/${selected.id}/tags/${e.target.value}`,
                          { method: "POST" },
                        ),
                      "Tag added.",
                    )
                  }
                >
                  <option value="">Choose a tag</option>
                  {tags
                    .filter(
                      (tag) =>
                        !selected.tags.some(
                          (existing) => existing.id === tag.id,
                        ),
                    )
                    .map((tag) => (
                      <option key={tag.id} value={tag.id}>
                        {tag.name}
                      </option>
                    ))}
                </select>
              </label>
              <div className="tag-list">
                {selected.tags.map((tag) => (
                  <button
                    key={tag.id}
                    style={{ borderColor: tag.color }}
                    onClick={() =>
                      change(
                        () =>
                          request(
                            `/api/v1/files/${selected.id}/tags/${tag.id}`,
                            { method: "DELETE" },
                          ),
                        "Tag removed.",
                      )
                    }
                  >
                    <TagIcon />
                    {tag.name} ×
                  </button>
                ))}
              </div>
              <h4>Version timeline</h4>
              <ol className="version-list">
                {versions.map((version) => (
                  <li
                    key={version.id}
                    className={version.id === selected.id ? "current" : ""}
                  >
                    <span>
                      {version.parent_file_id ? "Derived" : "Original"}
                    </span>
                    <b>{version.display_name}</b>
                    <small>
                      {new Date(version.created_at).toLocaleString()}
                    </small>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <div className="empty small">
              <Eye />
              <h3>Select a file</h3>
              <p>Preview and organize it here.</p>
            </div>
          )}
        </aside>
      </div>
      <div className="organizer">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (folderName)
              change(
                () =>
                  request("/api/v1/folders", {
                    method: "POST",
                    body: JSON.stringify({ name: folderName }),
                  }),
                "Folder created.",
              ).then(() => setFolderName(""));
          }}
        >
          <b>New folder</b>
          <input
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            placeholder="Folder name"
          />
          <button className="secondary">Create</button>
        </form>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (tagName)
              change(
                () =>
                  request("/api/v1/tags", {
                    method: "POST",
                    body: JSON.stringify({ name: tagName, color: "#176b4d" }),
                  }),
                "Tag created.",
              ).then(() => setTagName(""));
          }}
        >
          <b>New tag</b>
          <input
            value={tagName}
            onChange={(e) => setTagName(e.target.value)}
            placeholder="Tag name"
          />
          <button className="secondary">Create</button>
        </form>
      </div>
    </section>
  );
}

function AdminView() {
  const [stats, setStats] = useState<{
      users: number;
      files: number;
      storage_bytes: number;
      active_jobs: number;
    } | null>(null),
    [users, setUsers] = useState<User[]>([]),
    [engines, setEngines] = useState<Engine[]>([]),
    [adminCapabilities, setAdminCapabilities] = useState<
      Array<Capability & { enabled: boolean }>
    >([]),
    [fontCount, setFontCount] = useState<number | null>(null),
    [audit, setAudit] = useState<
      Array<{
        id: string;
        action: string;
        object_type: string;
        created_at: string;
      }>
    >([]),
    [appName, setAppName] = useState("ConvertVault"),
    [message, setMessage] = useState("");
  const loadAdmin = async () => {
    try {
      const [s, u, e, a, c, f] = await Promise.all([
        request<typeof stats>("/api/v1/admin/stats"),
        request<{ items: User[] }>("/api/v1/admin/users"),
        request<{ items: Engine[] }>("/api/v1/engines"),
        request<{
          items: Array<{
            id: string;
            action: string;
            object_type: string;
            created_at: string;
          }>;
        }>("/api/v1/admin/audit?page_size=20"),
        request<{ items: Array<Capability & { enabled: boolean }> }>(
          "/api/v1/admin/capabilities",
        ),
        request<{ families: string[] }>("/api/v1/admin/fonts"),
      ]);
      setStats(s);
      setUsers(u.items);
      setEngines(e.items);
      setAudit(a.items);
      setAdminCapabilities(c.items);
      setFontCount(f.families.length);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Admin data could not be loaded",
      );
    }
  };
  useEffect(() => {
    loadAdmin();
  }, []);
  return (
    <section className="admin-view">
      {message && <div className="notice">{message}</div>}
      <div className="stat-grid">
        <article>
          <Users />
          <b>{stats?.users ?? "—"}</b>
          <span>Users</span>
        </article>
        <article>
          <FolderOpen />
          <b>{stats?.files ?? "—"}</b>
          <span>Files</span>
        </article>
        <article>
          <Archive />
          <b>{stats ? size(stats.storage_bytes) : "—"}</b>
          <span>Storage</span>
        </article>
        <article>
          <RefreshCw />
          <b>{stats?.active_jobs ?? "—"}</b>
          <span>Active jobs</span>
        </article>
      </div>
      <div className="admin-grid">
        <article>
          <h3>Engine health</h3>
          {engines.map((engine) => (
            <div className="engine-row" key={engine.engine_id}>
              <span className={engine.available ? "healthy" : "offline"} />
              <div>
                <b>{engine.display_name}</b>
                <small>{engine.version}</small>
              </div>
              <strong>{engine.available ? "Available" : "Unavailable"}</strong>
            </div>
          ))}
          <h3>Capability controls</h3>
          <p className="muted">
            Disabled operations disappear immediately and are rejected before
            queueing.
          </p>
          <div className="capability-list">
            {adminCapabilities.map((capability, capabilityIndex) => (
              <label key={`${capability.engine_id}-${capability.operation}-${capabilityIndex}`}>
                <input
                  type="checkbox"
                  checked={capability.enabled}
                  onChange={(event) =>
                    request(
                      `/api/v1/admin/capabilities/${capability.operation}?enabled=${event.target.checked}`,
                      { method: "PUT" },
                    ).then(loadAdmin)
                  }
                />
                <span>
                  <b>{capability.operation.replaceAll(".", " ")}</b>
                  <small>{capability.engine_id}</small>
                </span>
              </label>
            ))}
          </div>
        </article>
        <article>
          <h3>Application identity</h3>
          <label>
            Application name
            <input
              value={appName}
              onChange={(e) => setAppName(e.target.value)}
            />
          </label>
          <button
            className="primary"
            onClick={() =>
              request(
                `/api/v1/admin/settings/app-name?value=${encodeURIComponent(appName)}`,
                { method: "PUT" },
              ).then(() => setMessage("Application name updated."))
            }
          >
            Save name
          </button>
          <h3>Users</h3>
          <p className="muted">
            {fontCount === null
              ? "Font scan unavailable"
              : `${fontCount} installed font families detected`}
          </p>
          {users.map((user) => (
            <div className="user-row" key={user.id}>
              <div className="avatar">{user.display_name[0]}</div>
              <div>
                <b>{user.display_name}</b>
                <small>{user.email}</small>
              </div>
              <span>{user.role}</span>
              <button
                className="text-button"
                onClick={() =>
                  request(`/api/v1/admin/users/${user.id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ is_active: !user.is_active }),
                  })
                    .then(loadAdmin)
                    .catch((error) => setMessage(error.message))
                }
              >
                {user.is_active ? "Deactivate" : "Activate"}
              </button>
            </div>
          ))}
        </article>
      </div>
      <article className="audit-table">
        <h3>Recent audit activity</h3>
        {audit.map((item) => (
          <div key={item.id}>
            <b>{item.action}</b>
            <span>{item.object_type}</span>
            <time>{new Date(item.created_at).toLocaleString()}</time>
          </div>
        ))}
      </article>
    </section>
  );
}
function JobList({ jobs }: { jobs: Job[] }) {
  return (
    <section className="jobs">
      {jobs.length === 0 ? (
        <div className="empty">
          <History />
          <h3>No conversion jobs yet</h3>
          <p>Completed and active work will appear here.</p>
        </div>
      ) : (
        jobs.map((job) => (
          <article key={job.id}>
            <div className={`status ${job.status}`}>
              {job.status === "succeeded" ? (
                <CheckCircle2 />
              ) : job.status === "failed" ? (
                <XCircle />
              ) : job.status === "queued" ? (
                <History />
              ) : job.status === "cancelled" ? (
                <XCircle />
              ) : (
                <RefreshCw />
              )}
            </div>
            <div className="job-main">
              <b>
                {job.operation.replaceAll(".", " ")} →{" "}
                {job.target_format.toUpperCase()}
              </b>
              <small>{new Date(job.created_at).toLocaleString()}</small>
              {job.status === "queued" && (
                <small className="job-message">
                  Waiting for a conversion worker…
                </small>
              )}
              {job.status === "running" && (
                <small className="job-message">Processing securely…</small>
              )}
              {job.warning && <p className="warning">{job.warning}</p>}
              {job.error_message && (
                <p className="error-text">{job.error_message}</p>
              )}
              <div className="progress">
                <span style={{ width: `${job.progress}%` }} />
              </div>
            </div>
            <div className="job-state">
              <strong>{job.status}</strong>
              <span>{job.progress}%</span>
            </div>
            {job.status === "succeeded" && job.output_file_id && (
              <DownloadButton fileId={job.output_file_id} />
            )}
          </article>
        ))
      )}
    </section>
  );
}
function DownloadButton({ fileId }: { fileId: string }) {
  return (
    <button
      className="icon-button"
      title="Download result"
      onClick={async () => {
        const response = await fetch(`${API}/api/v1/files/${fileId}/download`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem("access_token")}`,
          },
        });
        const blob = await response.blob();
        const anchor = document.createElement("a");
        anchor.href = URL.createObjectURL(blob);
        anchor.download = "convertvault-result";
        anchor.click();
        URL.revokeObjectURL(anchor.href);
      }}
    >
      <Download />
    </button>
  );
}
function SecurePreview({ file }: { file: VaultFile }) {
  const [url, setUrl] = useState(""),
    [text, setText] = useState("");
  useEffect(() => {
    let objectUrl = "",
      cancelled = false;
    if (
      !["image", "pdf"].includes(file.category) &&
      !file.mime_type.startsWith("text/")
    )
      return;
    fetch(`${API}/api/v1/files/${file.id}/download`, {
      headers: {
        Authorization: `Bearer ${localStorage.getItem("access_token")}`,
      },
    })
      .then((r) => r.blob())
      .then(async (blob) => {
        if (cancelled) return;
        if (file.mime_type.startsWith("text/"))
          setText((await blob.text()).slice(0, 4000));
        else {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl("");
      setText("");
    };
  }, [file.id, file.category, file.mime_type]);
  if (text) return <pre className="secure-preview text">{text}</pre>;
  if (!url) return null;
  return (
    <div className="secure-preview">
      {file.category === "image" ? (
        <img src={url} alt={`Preview of ${file.display_name}`} />
      ) : (
        <iframe
          src={`${url}#toolbar=0`}
          title={`Preview of ${file.display_name}`}
        />
      )}
      <span>
        <Eye /> Local preview
      </span>
    </div>
  );
}
