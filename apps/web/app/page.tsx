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

const API =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000`
    : "http://localhost:8000");
type User = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  quota_bytes: number;
};
type VaultFile = {
  id: string;
  display_name: string;
  extension: string;
  mime_type: string;
  category: string;
  size: number;
  checksum_sha256: string;
  status: string;
  created_at: string;
  parent_file_id: string | null;
  folder_id: string | null;
  is_favorite: boolean;
  tags: Tag[];
  meta: Record<string, unknown>;
};
type Job = {
  id: string;
  input_file_id: string;
  output_file_id: string | null;
  operation: string;
  target_format: string;
  status: string;
  progress: number;
  error_message: string | null;
  warning: string | null;
  created_at: string;
};
type Capability = {
  operation: string;
  source_extensions: string[];
  target_extensions: string[];
  engine_id: string;
  approximate: boolean;
  limitations: string[];
  options: Record<string, unknown>;
};
type Folder = { id: string; name: string; parent_id: string | null };
type Tag = { id: string; name: string; color: string };
type SavedPreset = {
  id: string;
  name: string;
  operation: string;
  target_format: string;
  options: Record<string, unknown>;
};
type Engine = {
  engine_id: string;
  display_name: string;
  available: boolean;
  version: string;
};
type PdfOperation = {
  kind: string;
  page?: number;
  pages?: number[];
  order?: number[];
  rect?: number[];
  points?: number[][];
  text?: string;
  replacement?: string;
  font?: string;
  font_size?: number;
  color?: string;
  fill?: string;
  width?: number;
  opacity?: number;
  rotation?: number;
  image_file_id?: string;
  uri?: string;
  field_name?: string;
  field_label?: string;
  field_value?: string;
  default_value?: string;
  required?: boolean;
  readonly?: boolean;
  hidden?: boolean;
  alignment?: string;
  format_type?: string;
  validation_pattern?: string;
  calculation?: string;
  choice_values?: string[];
  export_value?: string;
  max_length?: number;
  comb?: boolean;
  multiline?: boolean;
  password?: boolean;
  no_scroll?: boolean;
  tab_order?: number;
  search_terms?: string[];
  pattern_type?: string;
  custom_regex?: string;
  case_sensitive?: boolean;
  whole_word?: boolean;
  remove_metadata?: boolean;
  remove_comments?: boolean;
  remove_attachments?: boolean;
  remove_hidden_text?: boolean;
  remove_form_values?: boolean;
  attachment_name?: string;
  bookmark_title?: string;
  bookmark_level?: number;
  bookmark_index?: number;
  metadata?: Record<string, string>;
  object_id?: string;
  range_start?: number;
  range_end?: number;
  origin?: number[];
  font_resource?: string;
  font_xref?: number;
  reflow_policy?: string;
  font_policy?: string;
  source_xref?: number;
  source_digest?: string;
  source_rect?: number[];
  crop?: number[];
  vector_properties?: Record<string, unknown>;
  source_file_id?: string;
  source_page?: number;
  resize_mode?: string;
  page_width?: number;
  page_height?: number;
  page_boxes?: Record<string, number[]>;
  quads?: number[][];
  attachment_file_id?: string;
  annotation_name?: string;
  parent_annotation_name?: string;
  author?: string;
  subject?: string;
  annotation_status?: string;
  locked?: boolean;
  printable?: boolean;
  visible?: boolean;
  border_style?: string;
  line_start?: string;
  line_end?: string;
  stamp_type?: string;
  measurement_scale?: number;
  measurement_unit?: string;
};

type PdfRevision = {
  revision: number;
  operations: PdfOperation[];
  created_at: string;
};
type PdfProject = {
  id: string;
  name: string;
  source_file_id: string;
  output_file_id: string | null;
  operations: PdfOperation[];
  revision: number;
  status: string;
  updated_at: string;
};
type PdfDocumentInfo = {
  page_count: number;
  metadata: Record<string, string>;
  has_signatures: boolean;
  pages: Array<{
    page: number;
    width: number;
    height: number;
    rotation: number;
    fonts: string[];
    subset_fonts: string[];
    images: number;
    links: number;
    annotations: number;
    text_blocks: Array<{
      text: string;
      rect: number[];
      font: string;
      size: number;
      color: string;
    }>;
  }>;
};
type PdfWorkspaceDocument = {
  id: string;
  source_file_id: string;
  name: string;
  status: string;
};
type PdfWorkspaceSession = {
  id: string;
  document_id: string;
  base_version_id: string;
  status: string;
  revision: number;
  cursor: number;
  operations: PdfOperation[];
};
type PdfSceneText = {
  id: string;
  type: "text_run";
  page: number;
  bounds: number[];
  transform: number[];
  editability: string;
  text: string;
  style: {
    font?: string;
    font_size?: number;
    color?: string;
    subset?: boolean;
    font_resource?: string;
    font_xref?: number;
  };
};
type PdfSceneImage = {
  id: string;
  type: "image";
  page: number;
  bounds: number[];
  editability: string;
  lock_state: boolean;
  source: { xref?: number };
  properties: { width?: number; height?: number };
};
type PdfSceneVector = {
  id: string;
  type: "vector_path";
  page: number;
  bounds: number[];
  editability: string;
  lock_state: boolean;
  properties: {
    type?: string;
    width?: number;
    color?: number[];
    fill?: number[];
  };
};
type PdfSceneObject =
  | PdfSceneText
  | PdfSceneImage
  | PdfSceneVector
  | { type: string };

type PdfAnnotation = {
  id: string;
  xref: number;
  page: number;
  type: string;
  rect: number[];
  author: string;
  subject: string;
  comment: string;
  created_at: string;
  modified_at: string;
  status: string;
  parent_id: string | null;
  thread_id: string;
  reply_count: number;
  locked: boolean;
  printable: boolean;
  visible: boolean;
  opacity: number;
  color: string;
  fill: string | null;
  width: number;
  border_style: string;
  attachment?: Record<string, unknown> | null;
};

type PdfComparison = {
  before_file_id: string;
  after_file_id: string;
  before_name: string;
  after_name: string;
  summary: { total: number; by_type: Record<string, number> };
  differences: Array<{
    id: string;
    type: string;
    before_page: number | null;
    after_page: number | null;
    reviewed: boolean;
    details: Record<string, unknown>;
  }>;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const response = await fetch(`${API}${path}`, { ...options, headers });
  if (!response.ok) {
    const problem = await response
      .json()
      .catch(() => ({ detail: "Request failed" }));
    const detail = problem.detail;
    throw new Error(
      typeof detail === "string" ? detail : detail?.message || "Request failed",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
const size = (bytes: number) =>
  new Intl.NumberFormat(undefined, {
    style: "unit",
    unit: bytes > 1048576 ? "megabyte" : "kilobyte",
    maximumFractionDigits: 1,
  }).format(bytes / (bytes > 1048576 ? 1048576 : 1024));

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
        {tab === "editor" && <PdfStudio files={files} onJobsChanged={load} />}{" "}
        {tab === "jobs" && <JobList jobs={jobs} />}{" "}
        {tab === "admin" && user.role === "admin" && <AdminView />}
      </main>
    </div>
  );
}

function PdfStudio({
  files,
  onJobsChanged,
}: {
  files: VaultFile[];
  onJobsChanged: () => Promise<void>;
}) {
  const pdfs = files.filter((file) => file.extension === "pdf");
  const imageAssets = files.filter((file) => file.category === "image");
  const [projects, setProjects] = useState<PdfProject[]>([]);
  const [project, setProject] = useState<PdfProject | null>(null);
  const [workspaceSession, setWorkspaceSession] =
    useState<PdfWorkspaceSession | null>(null);
  const [sceneText, setSceneText] = useState<PdfSceneText[]>([]);
  const [sceneImages, setSceneImages] = useState<PdfSceneImage[]>([]);
  const [sceneVectors, setSceneVectors] = useState<PdfSceneVector[]>([]);
  const [annotations, setAnnotations] = useState<PdfAnnotation[]>([]);
  const [pageBoxes, setPageBoxes] = useState<Record<string, number[]>>({});
  const [documentInfo, setDocumentInfo] = useState<PdfDocumentInfo | null>(
    null,
  );
  const [revisions, setRevisions] = useState<PdfRevision[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [page, setPage] = useState(1);
  const [pageImage, setPageImage] = useState("");
  const [operations, setOperations] = useState<PdfOperation[]>([]);
  const [tool, setTool] = useState("select");
  const [text, setText] = useState("Text");
  const [replacement, setReplacement] = useState("");
  const [font, setFont] = useState("Helvetica");
  const [fontSize, setFontSize] = useState(12);
  const [color, setColor] = useState("#14211b");
  const [fill, setFill] = useState("#dff4e9");
  const [opacity, setOpacity] = useState(1);
  const [annotationKind, setAnnotationKind] = useState("annotate.highlight");
  const [annotationAuthor, setAnnotationAuthor] = useState("");
  const [annotationSubject, setAnnotationSubject] = useState("Review");
  const [annotationStatus, setAnnotationStatus] = useState("none");
  const [annotationBorder, setAnnotationBorder] = useState("solid");
  const [annotationWidth, setAnnotationWidth] = useState(2);
  const [annotationSearch, setAnnotationSearch] = useState("");
  const [annotationTypeFilter, setAnnotationTypeFilter] = useState("");
  const [annotationStatusFilter, setAnnotationStatusFilter] = useState("");
  const [annotationPageFilter, setAnnotationPageFilter] = useState("all");
  const [annotationSort, setAnnotationSort] = useState("page");
  const [hideResolved, setHideResolved] = useState(false);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState("");
  const [replyText, setReplyText] = useState("");
  const [attachmentId, setAttachmentId] = useState("");
  const [audioAnnotationsSupported, setAudioAnnotationsSupported] = useState(false);
  const [redactionPattern, setRedactionPattern] = useState("keyword");
  const [redactionTerms, setRedactionTerms] = useState("");
  const [redactionMetadata, setRedactionMetadata] = useState(false);
  const [redactionComments, setRedactionComments] = useState(false);
  const [redactionAttachments, setRedactionAttachments] = useState(false);
  const [redactionForms, setRedactionForms] = useState(false);
  const [compareFileId, setCompareFileId] = useState("");
  const [comparison, setComparison] = useState<PdfComparison | null>(null);
  const [comparisonMode, setComparisonMode] = useState("side-by-side");
  const [comparisonFilter, setComparisonFilter] = useState("");
  const [comparisonImages, setComparisonImages] = useState<Record<string, string>>({});
  const [bookmarks, setBookmarks] = useState<Array<{ index: number; level: number; title: string; page: number }>>([]);
  const [embeddedAttachments, setEmbeddedAttachments] = useState<Array<{ name: string; size?: number; description?: string }>>([]);
  const [bookmarkTitle, setBookmarkTitle] = useState("");
  const [attachmentAssetId, setAttachmentAssetId] = useState("");
  const [attachmentName, setAttachmentName] = useState("");
  const [imageId, setImageId] = useState("");
  const [pageSourceId, setPageSourceId] = useState("");
  const [pageSourceNumber, setPageSourceNumber] = useState(1);
  const [pageWidthValue, setPageWidthValue] = useState(595);
  const [pageHeightValue, setPageHeightValue] = useState(842);
  const [resizeMode, setResizeMode] = useState("fit");
  const [shapeKind, setShapeKind] = useState("rectangle");
  const [formKind, setFormKind] = useState("form.text");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const loadProjects = async () => {
    const response = await request<{ items: PdfProject[] }>(
      "/api/v1/pdf/projects",
    );
    setProjects(response.items);
    return response.items;
  };
  useEffect(() => {
    loadProjects().catch((error) => setNotice(error.message));
  }, []);
  useEffect(() => {
    if (!project) return;
    setWorkspaceSession(null);
    setSceneText([]);
    setSceneImages([]);
    setSceneVectors([]);
    setPageBoxes({});
    setOperations(project.operations);
    setPage(1);
    Promise.all([
      request<PdfDocumentInfo>(`/api/v1/pdf/projects/${project.id}/document`),
      request<{ items: PdfRevision[] }>(
        `/api/v1/pdf/projects/${project.id}/revisions`,
      ),
    ])
      .then(([info, history]) => {
        setDocumentInfo(info);
        setRevisions(history.items);
      })
      .catch((error) => setNotice(error.message));
    (async () => {
      const documents = await request<{ items: PdfWorkspaceDocument[] }>(
        "/api/v1/pdf/documents",
      );
      let document = documents.items.find(
        (item) => item.source_file_id === project.source_file_id,
      );
      if (!document) {
        document = await request<PdfWorkspaceDocument>(
          "/api/v1/pdf/documents",
          {
            method: "POST",
            body: JSON.stringify({
              file_id: project.source_file_id,
              name: project.name,
            }),
          },
        );
      }
      const sessions = await request<{ items: PdfWorkspaceSession[] }>(
        `/api/v1/pdf/documents/${document.id}/sessions`,
      );
      let session = sessions.items.find((item) => item.status === "active");
      if (!session) {
        session = await request<PdfWorkspaceSession>(
          `/api/v1/pdf/documents/${document.id}/sessions`,
          { method: "POST", body: JSON.stringify({}) },
        );
      }
      setWorkspaceSession(session);
      if (session.operations.length) setOperations(session.operations);
    })().catch((error) =>
      setNotice(
        error instanceof Error
          ? error.message
          : "The command workspace could not be opened",
      ),
    );
  }, [project?.id]);
  useEffect(() => {
    if (!workspaceSession) return;
    request<{ objects: PdfSceneObject[]; boxes: Record<string, number[]> }>(
      `/api/v1/pdf/sessions/${workspaceSession.id}/scene?page=${page}`,
    )
      .then((scene) => {
        setSceneText(
          scene.objects.filter(
            (item): item is PdfSceneText => item.type === "text_run",
          ),
        );
        setSceneImages(
          scene.objects.filter(
            (item): item is PdfSceneImage => item.type === "image",
          ),
        );
        setSceneVectors(
          scene.objects.filter(
            (item): item is PdfSceneVector => item.type === "vector_path",
          ),
        );
        setPageBoxes(scene.boxes);
        const media = scene.boxes.media;
        if (media) {
          setPageWidthValue(Math.round((media[2] - media[0]) * 100) / 100);
          setPageHeightValue(Math.round((media[3] - media[1]) * 100) / 100);
        }
      })
      .catch((error) => setNotice(error.message));
  }, [workspaceSession?.id, workspaceSession?.revision, page]);
  useEffect(() => {
    if (!workspaceSession) return;
    request<PdfDocumentInfo>(
      `/api/v1/pdf/sessions/${workspaceSession.id}/document`,
    )
      .then((info) => {
        setDocumentInfo(info);
        setPage((current) => Math.min(current, info.page_count));
      })
      .catch((error) => setNotice(error.message));
  }, [workspaceSession?.id, workspaceSession?.revision]);
  useEffect(() => {
    if (!workspaceSession) return;
    const params = new URLSearchParams();
    if (annotationSearch) params.set("search", annotationSearch);
    if (annotationTypeFilter) params.set("type", annotationTypeFilter);
    if (annotationStatusFilter) params.set("status", annotationStatusFilter);
    if (annotationPageFilter === "current") params.set("page", String(page));
    if (hideResolved) params.set("hide_resolved", "true");
    params.set("sort", annotationSort);
    request<{
      items: PdfAnnotation[];
      audio_supported: boolean;
    }>(`/api/v1/pdf/sessions/${workspaceSession.id}/annotations?${params}`)
      .then((response) => {
        setAnnotations(response.items);
        setAudioAnnotationsSupported(response.audio_supported);
      })
      .catch((error) => setNotice(error.message));
  }, [
    workspaceSession?.id,
    workspaceSession?.revision,
    annotationSearch,
    annotationTypeFilter,
    annotationStatusFilter,
    annotationPageFilter,
    annotationSort,
    hideResolved,
    page,
  ]);
  useEffect(() => {
    if (!workspaceSession) return;
    request<{ bookmarks: typeof bookmarks; attachments: typeof embeddedAttachments }>(
      `/api/v1/pdf/sessions/${workspaceSession.id}/navigation`,
    ).then((response) => {
      setBookmarks(response.bookmarks);
      setEmbeddedAttachments(response.attachments);
    }).catch((error) => setNotice(error.message));
  }, [workspaceSession?.id, workspaceSession?.revision]);
  useEffect(() => {
    if (!project) return;
    let active = true;
    const token = localStorage.getItem("access_token");
    const previewPath = workspaceSession
      ? `/api/v1/pdf/sessions/${workspaceSession.id}/pages/${page}/render?dpi=120`
      : `/api/v1/pdf/projects/${project.id}/pages/${page}/render?dpi=120`;
    fetch(`${API}${previewPath}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((response) => {
        if (!response.ok) throw new Error("Page preview could not be rendered");
        return response.blob();
      })
      .then((blob) => {
        if (!active) return;
        const url = URL.createObjectURL(blob);
        setPageImage((old) => {
          if (old) URL.revokeObjectURL(old);
          return url;
        });
      })
      .catch((error) => setNotice(error.message));
    return () => {
      active = false;
    };
  }, [project?.id, workspaceSession?.id, workspaceSession?.revision, page]);

  async function createProject() {
    if (!sourceId) return;
    setBusy(true);
    try {
      const source = pdfs.find((file) => file.id === sourceId);
      const created = await request<PdfProject>("/api/v1/pdf/projects", {
        method: "POST",
        body: JSON.stringify({
          file_id: sourceId,
          name: source ? `${source.display_name} studio project` : undefined,
        }),
      });
      await loadProjects();
      setProject(created);
      setNotice("PDF Studio project created. The original remains untouched.");
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Could not create project",
      );
    } finally {
      setBusy(false);
    }
  }

  async function syncCommandSession() {
    if (!workspaceSession) return null;
    let current = workspaceSession;
    let common = 0;
    while (
      common < current.operations.length &&
      common < operations.length &&
      JSON.stringify(current.operations[common]) ===
        JSON.stringify(operations[common])
    )
      common += 1;
    for (let index = current.operations.length; index > common; index -= 1) {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${current.id}/undo`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: current.revision,
            idempotency_key: `ui-undo-${crypto.randomUUID()}`,
          }),
        },
      );
      current = result.session;
    }
    for (const operation of operations.slice(common)) {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${current.id}/commands`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: current.revision,
            idempotency_key: `ui-command-${crypto.randomUUID()}`,
            operation,
            object_id: operation.object_id,
          }),
        },
      );
      current = result.session;
    }
    setWorkspaceSession(current);
    setOperations(current.operations);
    return current;
  }

  async function saveProject() {
    if (!project) return null;
    setBusy(true);
    try {
      const commandSession = await syncCommandSession();
      const saved = await request<PdfProject>(
        `/api/v1/pdf/projects/${project.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            expected_revision: project.revision,
            operations,
          }),
        },
      );
      setProject(saved);
      await loadProjects();
      const history = await request<{ items: PdfRevision[] }>(
        `/api/v1/pdf/projects/${saved.id}/revisions`,
      );
      setRevisions(history.items);
      setNotice(
        `Revision ${saved.revision} saved with ${commandSession?.cursor ?? operations.length} recoverable commands.`,
      );
      return { project: saved, session: commandSession };
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Could not save edits",
      );
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    const saved = await saveProject();
    if (!saved) return;
    setBusy(true);
    try {
      if (saved.session) {
        await request(`/api/v1/pdf/sessions/${saved.session.id}/exports`, {
          method: "POST",
          body: JSON.stringify({
            expected_revision: saved.session.revision,
            idempotency_key: `ui-export-${crypto.randomUUID()}`,
          }),
        });
        setWorkspaceSession({
          ...saved.session,
          revision: saved.session.revision + 1,
          status: "exporting",
        });
      } else {
        await request(`/api/v1/pdf/projects/${saved.project.id}/publish`, {
          method: "POST",
        });
      }
      setProject({ ...saved.project, status: "queued" });
      setNotice(
        "High-fidelity PDF export queued. The result will appear in your library.",
      );
      await onJobsChanged();
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "Could not export PDF",
      );
    } finally {
      setBusy(false);
    }
  }

  async function historyAction(action: "undo" | "redo") {
    if (!workspaceSession) {
      if (action === "undo") setOperations((current) => current.slice(0, -1));
      return;
    }
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/${action}`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-${action}-${crypto.randomUUID()}`,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        `${action === "undo" ? "Undid" : "Redid"} the last editor command.`,
      );
    } catch (error) {
      setNotice(error instanceof Error ? error.message : `Could not ${action}`);
    } finally {
      setBusy(false);
    }
  }

  async function createAnnotationOperation(operation: PdfOperation) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-${crypto.randomUUID()}`,
            operation,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice("Annotation added to the recoverable PDF history.");
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : "The annotation could not be added",
      );
    } finally {
      setBusy(false);
    }
  }

  async function updateAnnotation(
    annotation: PdfAnnotation,
    changes: Record<string, unknown>,
  ) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations/${encodeURIComponent(annotation.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-update-${crypto.randomUUID()}`,
            ...changes,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice("Annotation properties updated.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The annotation could not be updated");
    } finally {
      setBusy(false);
    }
  }

  async function replyToAnnotation(annotation: PdfAnnotation) {
    if (!workspaceSession || !replyText.trim()) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations/${encodeURIComponent(annotation.id)}/replies`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-reply-${crypto.randomUUID()}`,
            text: replyText.trim(),
            author: annotationAuthor || undefined,
            subject: "Reply",
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setReplyText("");
      setNotice("Reply added to the annotation thread.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The reply could not be added");
    } finally {
      setBusy(false);
    }
  }

  async function deleteAnnotation(annotation: PdfAnnotation) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations/${encodeURIComponent(annotation.id)}`,
        {
          method: "DELETE",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-delete-${crypto.randomUUID()}`,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setSelectedAnnotationId("");
      setNotice("Annotation deleted. Undo can restore it.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The annotation could not be deleted");
    } finally {
      setBusy(false);
    }
  }

  async function applySearchRedaction() {
    if (!workspaceSession) return;
    const terms = redactionTerms.split(/[\n,]/).map((value) => value.trim()).filter(Boolean);
    if (redactionPattern === "keyword" && !terms.length) {
      setNotice("Enter at least one keyword to redact.");
      return;
    }
    setBusy(true);
    try {
      const operation: PdfOperation = {
        kind: "redact.search",
        pages: documentInfo?.pages.map((item) => item.page),
        search_terms: terms,
        pattern_type: redactionPattern,
        custom_regex: redactionPattern === "custom_regex" ? replacement : undefined,
        fill: "#000000",
        color: "#ffffff",
        remove_metadata: redactionMetadata,
        remove_comments: redactionComments,
        remove_attachments: redactionAttachments,
        remove_hidden_text: true,
        remove_form_values: redactionForms,
      };
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/commands`,
        { method: "POST", body: JSON.stringify({
          expected_revision: workspaceSession.revision,
          idempotency_key: `ui-search-redaction-${crypto.randomUUID()}`,
          operation,
        }) },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice("Search redaction applied to recoverable history. Export validation will confirm no matches remain.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Search redaction could not be applied");
    } finally {
      setBusy(false);
    }
  }

  async function loadComparisonImages(afterFileId: string, comparisonPage = 1) {
    if (!project) return;
    const token = localStorage.getItem("access_token");
    const entries = await Promise.all(["before", "after", "overlay"].map(async (side) => {
      const params = new URLSearchParams({ before_file_id: project.source_file_id,
        after_file_id: afterFileId, side, page: String(comparisonPage), dpi: "96" });
      const response = await fetch(`${API}/api/v1/pdf/compare/render?${params}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error("Comparison preview could not be rendered");
      return [side, URL.createObjectURL(await response.blob())] as const;
    }));
    setComparisonImages((current) => {
      Object.values(current).forEach((url) => URL.revokeObjectURL(url));
      return Object.fromEntries(entries);
    });
  }

  async function compareDocuments() {
    if (!project || !compareFileId) return;
    setBusy(true);
    try {
      const report = await request<PdfComparison>("/api/v1/pdf/compare", {
        method: "POST",
        body: JSON.stringify({ before_file_id: project.source_file_id, after_file_id: compareFileId,
          ignore_headers_footers: false, ignore_formatting: false, ignore_whitespace: true }),
      });
      setComparison(report);
      const firstPage = report.differences.find((item) => item.after_page || item.before_page);
      await loadComparisonImages(compareFileId, firstPage?.after_page || firstPage?.before_page || 1);
      setNotice(`Comparison found ${report.summary.total} text, object, page, metadata, and visual differences.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The PDFs could not be compared");
    } finally {
      setBusy(false);
    }
  }

  function exportComparisonReport() {
    if (!comparison) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(comparison, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "pdf-comparison-report.json"; anchor.click();
    URL.revokeObjectURL(url);
  }

  async function applyNavigationOperation(operation: PdfOperation) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/commands`,
        { method: "POST", body: JSON.stringify({ expected_revision: workspaceSession.revision,
          idempotency_key: `ui-navigation-${crypto.randomUUID()}`, operation }) },
      );
      setWorkspaceSession(result.session); setOperations(result.session.operations);
      setNotice("Document navigation or embedded-file command added to recoverable history.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The document navigation command failed");
    } finally { setBusy(false); }
  }

  async function downloadEmbeddedAttachment(name: string) {
    if (!workspaceSession) return;
    const token = localStorage.getItem("access_token");
    const response = await fetch(`${API}/api/v1/pdf/sessions/${workspaceSession.id}/attachments/download?name=${encodeURIComponent(name)}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!response.ok) { setNotice("The embedded attachment could not be downloaded"); return; }
    const url = URL.createObjectURL(await response.blob()); const anchor = document.createElement("a");
    anchor.href = url; anchor.download = name; anchor.click(); URL.revokeObjectURL(url);
  }

  function addOperation(event: React.MouseEvent<HTMLDivElement>) {
    if (!documentInfo || tool === "select") return;
    const pageInfo = documentInfo.pages[page - 1];
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * pageInfo.width;
    const y = ((event.clientY - bounds.top) / bounds.height) * pageInfo.height;
    const rect = [
      Math.max(0, x - 5),
      Math.max(0, y - 5),
      Math.min(pageInfo.width, x + (tool === "comment" ? 25 : 180)),
      Math.min(pageInfo.height, y + (tool === "comment" ? 25 : 45)),
    ];
    const base = {
      page,
      rect,
      color,
      fill,
      opacity,
      font,
      font_size: fontSize,
    };
    let operation: PdfOperation | null = null;
    if (tool === "text")
      operation = { kind: "content.add_text", ...base, text };
    if (tool === "shape")
      operation = { kind: "content.add_shape", ...base, text: shapeKind };
    if (tool === "highlight")
      operation = { kind: "annotate.highlight", ...base };
    if (tool === "underline")
      operation = { kind: "annotate.underline", ...base };
    if (tool === "strikeout")
      operation = { kind: "annotate.strikeout", ...base };
    if (tool === "comment")
      operation = { kind: "annotate.comment", ...base, text };
    if (tool === "free_text")
      operation = { kind: "annotate.free_text", ...base, text };
    if (tool === "annotation") {
      operation = {
        kind: annotationKind,
        ...base,
        text:
          [
            "annotate.comment",
            "annotate.free_text",
            "annotate.callout",
            "annotate.replace_text",
            "annotate.redaction_mark",
          ].includes(annotationKind)
            ? text
            : undefined,
        author: annotationAuthor || undefined,
        subject: annotationSubject || undefined,
        annotation_status: annotationStatus,
        border_style: annotationBorder,
        width: annotationWidth,
        printable: true,
        visible: true,
        locked: false,
        attachment_file_id:
          annotationKind === "annotate.attachment" ? attachmentId : undefined,
        stamp_type: annotationKind === "annotate.stamp" ? "approved" : undefined,
        measurement_scale:
          annotationKind === "annotate.measurement" ? 1 : undefined,
        measurement_unit:
          annotationKind === "annotate.measurement" ? "pt" : undefined,
      };
      if (
        ["annotate.line", "annotate.arrow", "annotate.measurement"].includes(
          annotationKind,
        )
      )
        operation.points = [
          [rect[0], rect[1]],
          [rect[2], rect[3]],
        ];
      if (annotationKind === "annotate.ink")
        operation.points = [
          [x - 30, y + 10],
          [x, y - 10],
          [x + 30, y + 10],
        ];
      if (["annotate.polygon", "annotate.polyline"].includes(annotationKind))
        operation.points = [
          [x - 40, y + 20],
          [x, y - 25],
          [x + 40, y + 20],
        ];
      if (annotationKind === "annotate.callout")
        operation.points = [
          [x - 25, y + 20],
          [x, y],
        ];
    }
    if (tool === "redact") operation = { kind: "redact", ...base };
    if (tool === "crop") operation = { kind: "page.crop", ...base };
    if (tool === "link") operation = { kind: "link.add", ...base, uri: text };
    if (tool === "form")
      operation = {
        kind: formKind,
        ...base,
        field_name: text || `field_${operations.length + 1}`,
        field_label: text || `Field ${operations.length + 1}`,
        field_value: replacement,
        choice_values: ["form.radio", "form.combo", "form.listbox"].includes(formKind)
          ? (replacement || "Option 1, Option 2").split(",").map((value) => value.trim()).filter(Boolean)
          : undefined,
        multiline: formKind === "form.multiline",
        format_type:
          formKind === "form.date" ? "date" : formKind === "form.numeric" ? "number" : "none",
      };
    if (tool === "draw")
      operation = {
        kind: "content.draw",
        page,
        points: [
          [x - 20, y],
          [x, y - 15],
          [x + 20, y],
        ],
        color,
        width: 2,
        opacity,
      };
    if (["image", "signature"].includes(tool) && imageId)
      operation = {
        kind: tool === "image" ? "content.add_image" : "signature.add",
        ...base,
        image_file_id: imageId,
      };
    if (operation) {
      if (operation.kind.startsWith("annotate.") && workspaceSession) {
        if (operation.kind === "annotate.attachment" && !attachmentId) {
          setNotice("Choose a vault file to attach first.");
          return;
        }
        void createAnnotationOperation(operation);
        return;
      }
      setOperations((current) => [...current, operation as PdfOperation]);
      setNotice(
        `${tool} edit added to page ${page}. Save to create a revision.`,
      );
    } else if (["image", "signature"].includes(tool)) {
      setNotice("Choose an image asset first.");
    }
  }

  function pageAction(kind: "rotate" | "delete" | "blank") {
    if (!documentInfo) return;
    if (kind === "rotate")
      setOperations((current) => [
        ...current,
        { kind: "page.rotate", page, rotation: 90 },
      ]);
    if (kind === "delete" && documentInfo.page_count > 1)
      setOperations((current) => [
        ...current,
        { kind: "page.delete", pages: [page] },
      ]);
    if (kind === "blank")
      setOperations((current) => [
        ...current,
        { kind: "page.insert_blank", page: page + 1 },
      ]);
  }

  function movePage(direction: -1 | 1) {
    if (!documentInfo) return;
    const lastOrder = [...operations]
      .reverse()
      .find((operation) => operation.kind === "page.reorder")?.order;
    const order = lastOrder
      ? [...lastOrder]
      : Array.from(
          { length: documentInfo.page_count },
          (_, index) => index + 1,
        );
    const index = order.indexOf(page);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    setOperations((current) => [...current, { kind: "page.reorder", order }]);
  }

  async function restoreRevision(revision: number) {
    if (!project) return;
    const restored = await request<PdfProject>(
      `/api/v1/pdf/projects/${project.id}/restore/${revision}`,
      { method: "POST" },
    );
    setProject(restored);
    setOperations(restored.operations);
    setNotice(
      `Revision ${revision} restored as revision ${restored.revision}.`,
    );
  }

  function addDocumentOperation(
    kind: "watermark.text" | "header_footer" | "metadata.set",
  ) {
    if (kind === "metadata.set") {
      setOperations((current) => [
        ...current,
        { kind, metadata: { title: text } },
      ]);
      setNotice("Document title metadata queued.");
      return;
    }
    setOperations((current) => [
      ...current,
      {
        kind,
        text,
        font_size:
          kind === "watermark.text" ? fontSize : Math.min(fontSize, 24),
        color,
        opacity,
      },
    ]);
    setNotice(
      kind === "watermark.text"
        ? "Watermark queued for every page."
        : "Footer queued for every page. Use {page} for page numbers.",
    );
  }

  async function replaceExistingText(textObject: PdfSceneText) {
    if (!workspaceSession) {
      setNotice(
        "The recoverable command session is still opening. Try again in a moment.",
      );
      return;
    }
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/text/${textObject.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-native-text-${crypto.randomUUID()}`,
            operation: "replace_range",
            range: { start: 0, end: textObject.text.length },
            text: replacement,
            reflow_policy: "preserve_line_positions",
            font_policy: "preserve_or_prompt",
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setText(textObject.text);
      setNotice(
        `Native text object edited on page ${page}. Font, size, colour, and baseline are preserved where the PDF permits it.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "Native text could not be edited",
      );
    } finally {
      setBusy(false);
    }
  }

  async function editExistingImage(
    image: PdfSceneImage,
    action: "move" | "resize" | "rotate" | "crop" | "replace" | "delete",
  ) {
    if (!workspaceSession) return;
    const [x0, y0, x1, y1] = image.bounds;
    const payload: Record<string, unknown> = {
      expected_revision: workspaceSession.revision,
      idempotency_key: `ui-image-${crypto.randomUUID()}`,
      action:
        action === "delete"
          ? "delete"
          : action === "replace"
            ? "replace"
            : "transform",
      rect:
        action === "move"
          ? [x0 + 18, y0 + 18, x1 + 18, y1 + 18]
          : action === "resize"
            ? [x0, y0, x1 + (x1 - x0) * 0.2, y1 + (y1 - y0) * 0.2]
            : image.bounds,
      rotation: action === "rotate" ? 15 : 0,
      crop: action === "crop" ? [0.1, 0.1, 0.9, 0.9] : undefined,
      image_file_id: action === "replace" ? imageId : undefined,
    };
    if (action === "replace" && !imageId) {
      setNotice("Choose a replacement image asset first.");
      return;
    }
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/images/${image.id}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        `Existing image ${action} command applied and added to recoverable history.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "The image could not be edited",
      );
    } finally {
      setBusy(false);
    }
  }

  async function editExistingVector(
    vector: PdfSceneVector,
    action: "move" | "resize" | "rotate" | "restyle" | "delete",
  ) {
    if (!workspaceSession) return;
    const [x0, y0, x1, y1] = vector.bounds;
    const payload = {
      expected_revision: workspaceSession.revision,
      idempotency_key: `ui-vector-${crypto.randomUUID()}`,
      action: action === "delete" ? "delete" : "transform",
      rect:
        action === "move"
          ? [x0 + 18, y0 + 18, x1 + 18, y1 + 18]
          : action === "resize"
            ? [x0, y0, x1 + (x1 - x0) * 0.2, y1 + (y1 - y0) * 0.2]
            : vector.bounds,
      rotation: action === "rotate" ? 15 : 0,
      color: action === "restyle" ? color : undefined,
      fill: action === "restyle" ? fill : undefined,
      width: action === "restyle" ? 3 : undefined,
      opacity: action === "restyle" ? opacity : undefined,
    };
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/vectors/${vector.id}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        `Existing vector ${action} command applied and added to recoverable history.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "The vector could not be edited",
      );
    } finally {
      setBusy(false);
    }
  }

  async function importExistingPage(action: "insert" | "replace") {
    if (!workspaceSession || !pageSourceId) {
      setNotice("Choose a source PDF before importing a page.");
      return;
    }
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/pages/import`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-page-import-${crypto.randomUUID()}`,
            action,
            page: action === "insert" ? page + 1 : page,
            source_file_id: pageSourceId,
            source_page: pageSourceNumber,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        action === "insert"
          ? `Page ${pageSourceNumber} will be inserted after page ${page}. Interactive objects are preserved.`
          : `Page ${page} will be replaced from the selected PDF. Interactive objects are preserved.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "The page could not be imported",
      );
    } finally {
      setBusy(false);
    }
  }

  async function updatePageGeometry(action: "resize" | "set_boxes") {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/pages/${page}/geometry`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-page-geometry-${crypto.randomUUID()}`,
            action,
            width: action === "resize" ? pageWidthValue : undefined,
            height: action === "resize" ? pageHeightValue : undefined,
            resize_mode: resizeMode,
            boxes: action === "set_boxes" ? pageBoxes : {},
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        action === "resize"
          ? `Page ${page} resized to ${pageWidthValue} × ${pageHeightValue} points with ${resizeMode} scaling.`
          : `Page ${page} media, crop, bleed, trim, and art boxes were added to recoverable history.`,
      );
    } catch (error) {
      setNotice(
        error instanceof Error
          ? error.message
          : "Page geometry could not be updated",
      );
    } finally {
      setBusy(false);
    }
  }

  function updateBox(name: string, value: string) {
    const coordinates = value
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item));
    setPageBoxes((current) => ({ ...current, [name]: coordinates }));
  }

  if (!project)
    return (
      <section className="studio-welcome">
        <div>
          <p className="eyebrow">NON-DESTRUCTIVE PDF WORKSPACE</p>
          <h2>Edit every layer you can safely change</h2>
          <p className="muted">
            Organize pages, edit and add content, permanently redact, annotate,
            create links and form fields, add graphics and signatures, then
            export a new validated PDF. Your source file is always preserved.
          </p>
          <div className="studio-start">
            <select
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
            >
              <option value="">Choose a PDF from your library</option>
              {pdfs.map((file) => (
                <option key={file.id} value={file.id}>
                  {file.display_name}
                </option>
              ))}
            </select>
            <button
              className="primary"
              onClick={createProject}
              disabled={!sourceId || busy}
            >
              <Plus /> New editing project
            </button>
          </div>
          {!pdfs.length && (
            <p className="warning">
              Upload a PDF in Convert or Library to begin.
            </p>
          )}
        </div>
        {!!projects.length && (
          <div className="project-list">
            <p className="eyebrow">RECENT PROJECTS</p>
            {projects.map((item) => (
              <button key={item.id} onClick={() => setProject(item)}>
                <FileText />
                <span>
                  <b>{item.name}</b>
                  <small>
                    Revision {item.revision} · {item.status}
                  </small>
                </span>
                <ChevronRight />
              </button>
            ))}
          </div>
        )}
        {notice && <div className="notice">{notice}</div>}
      </section>
    );

  const pageInfo = documentInfo?.pages[page - 1];
  const pageOps = operations.filter(
    (operation) => operation.page === page && operation.rect,
  );
  const selectedAnnotation = annotations.find(
    (annotation) => annotation.id === selectedAnnotationId,
  );
  const tools = [
    ["select", MousePointer2, "Select"],
    ["text", Type, "Text"],
    ["shape", Square, "Shape"],
    ["draw", PenTool, "Draw"],
    ["annotation", Highlighter, "Annotate"],
    ["redact", Eraser, "Redact"],
    ["crop", Square, "Crop"],
    ["link", Link2, "Link"],
    ["form", FileText, "Form field"],
    ["image", Plus, "Image"],
    ["signature", PenTool, "Signature"],
  ] as const;
  return (
    <section className="pdf-studio">
      <div className="studio-commandbar">
        <button className="secondary" onClick={() => setProject(null)}>
          <ChevronLeft /> Projects
        </button>
        <div>
          <b>{project.name}</b>
          <small>
            Revision {workspaceSession?.revision ?? project.revision} ·{" "}
            {operations.length} commands ·{" "}
            {workspaceSession?.status ?? project.status}
          </small>
        </div>
        <button
          className="secondary"
          onClick={() => historyAction("undo")}
          disabled={!operations.length}
        >
          <Undo2 /> Undo
        </button>
        <button
          className="secondary"
          onClick={() => historyAction("redo")}
          disabled={!workspaceSession}
        >
          <Redo2 /> Redo
        </button>
        <button className="secondary" onClick={saveProject} disabled={busy}>
          <Save /> Save
        </button>
        <button className="primary" onClick={publish} disabled={busy}>
          <Download /> Export PDF
        </button>
      </div>
      {documentInfo?.has_signatures && (
        <div className="signature-warning">
          This PDF contains a digital signature. Editing preserves the original,
          but the exported copy cannot retain the original signature validity.
        </div>
      )}
      {notice && (
        <div className="notice" onClick={() => setNotice("")}>
          {notice}
        </div>
      )}
      <div className="studio-layout">
        <aside className="page-rail">
          <b>Pages</b>
          {documentInfo?.pages.map((item) => (
            <button
              key={item.page}
              className={page === item.page ? "active" : ""}
              onClick={() => setPage(item.page)}
            >
              <span>{item.page}</span>
              <small>
                {Math.round(item.width)} × {Math.round(item.height)}
              </small>
            </button>
          ))}
          <div className="page-actions">
            <button title="Move page left" onClick={() => movePage(-1)}>
              <ChevronLeft />
            </button>
            <button title="Move page right" onClick={() => movePage(1)}>
              <ChevronRight />
            </button>
            <button title="Rotate page" onClick={() => pageAction("rotate")}>
              <RotateCw />
            </button>
            <button
              title="Insert blank page"
              onClick={() => pageAction("blank")}
            >
              <Plus />
            </button>
            <button title="Delete page" onClick={() => pageAction("delete")}>
              <Trash2 />
            </button>
          </div>
        </aside>
        <div className="studio-canvas-area">
          <div className="studio-toolbar">
            {tools.map(([id, Icon, label]) => (
              <button
                key={id}
                className={tool === id ? "active" : ""}
                onClick={() => setTool(id)}
                title={label}
              >
                <Icon />
                <span>{label}</span>
              </button>
            ))}
          </div>
          <div
            className="pdf-page"
            onClick={addOperation}
            style={
              pageInfo
                ? { aspectRatio: `${pageInfo.width}/${pageInfo.height}` }
                : undefined
            }
          >
            {pageImage ? (
              <img src={pageImage} alt={`PDF page ${page}`} />
            ) : (
              <div className="loader" />
            )}
            {pageInfo &&
              pageOps.map((operation, index) => {
                const rect = operation.rect as number[];
                return (
                  <div
                    key={`${operation.kind}-${index}`}
                    className={`edit-overlay ${operation.kind.replaceAll(".", "-")}`}
                    style={{
                      left: `${(rect[0] / pageInfo.width) * 100}%`,
                      top: `${(rect[1] / pageInfo.height) * 100}%`,
                      width: `${((rect[2] - rect[0]) / pageInfo.width) * 100}%`,
                      height: `${((rect[3] - rect[1]) / pageInfo.height) * 100}%`,
                      borderColor: operation.color,
                      background:
                        operation.kind === "redact"
                          ? "#111"
                          : `${operation.fill || operation.color || "#176b4d"}35`,
                      opacity: operation.opacity,
                    }}
                  >
                    <span>
                      {operation.kind.includes("text")
                        ? operation.text
                        : operation.kind.split(".").pop()}
                    </span>
                  </div>
                );
              })}
          </div>
          <div className="page-stepper">
            <button onClick={() => setPage(Math.max(1, page - 1))}>
              <ChevronLeft />
            </button>
            <span>
              Page {page} of {documentInfo?.page_count || 0}
            </span>
            <button
              onClick={() =>
                setPage(Math.min(documentInfo?.page_count || 1, page + 1))
              }
            >
              <ChevronRight />
            </button>
          </div>
        </div>
        <aside className="studio-properties">
          <p className="eyebrow">TOOL PROPERTIES</p>
          <h3>{tools.find(([id]) => id === tool)?.[2]}</h3>
          {tool === "annotation" && (
            <div className="annotation-properties">
              <label>
                Annotation type
                <select
                  value={annotationKind}
                  onChange={(event) => setAnnotationKind(event.target.value)}
                >
                  <optgroup label="Text markup">
                    <option value="annotate.highlight">Highlight</option>
                    <option value="annotate.underline">Underline</option>
                    <option value="annotate.squiggly">Squiggly underline</option>
                    <option value="annotate.strikeout">Strikeout</option>
                    <option value="annotate.replace_text">Replace-text suggestion</option>
                    <option value="annotate.caret">Caret insertion</option>
                  </optgroup>
                  <optgroup label="Comments and drawing">
                    <option value="annotate.comment">Text note</option>
                    <option value="annotate.free_text">Text box</option>
                    <option value="annotate.callout">Callout</option>
                    <option value="annotate.ink">Freehand ink</option>
                    <option value="annotate.line">Line</option>
                    <option value="annotate.arrow">Arrow</option>
                    <option value="annotate.rectangle">Rectangle</option>
                    <option value="annotate.ellipse">Ellipse</option>
                    <option value="annotate.polygon">Polygon</option>
                    <option value="annotate.polyline">Polyline</option>
                  </optgroup>
                  <optgroup label="Review and evidence">
                    <option value="annotate.stamp">Stamp</option>
                    <option value="annotate.attachment">File attachment</option>
                    <option value="annotate.redaction_mark">Redaction mark</option>
                    <option value="annotate.measurement">Measurement</option>
                  </optgroup>
                </select>
              </label>
              {[
                "annotate.comment",
                "annotate.free_text",
                "annotate.callout",
                "annotate.replace_text",
                "annotate.redaction_mark",
              ].includes(annotationKind) && (
                <label>
                  Comment or replacement
                  <textarea value={text} onChange={(event) => setText(event.target.value)} />
                </label>
              )}
              <label>
                Author
                <input value={annotationAuthor} onChange={(event) => setAnnotationAuthor(event.target.value)} />
              </label>
              <label>
                Subject
                <input value={annotationSubject} onChange={(event) => setAnnotationSubject(event.target.value)} />
              </label>
              <label>
                Review status
                <select value={annotationStatus} onChange={(event) => setAnnotationStatus(event.target.value)}>
                  <option value="none">No status</option>
                  <option value="open">Open</option>
                  <option value="accepted">Accepted</option>
                  <option value="rejected">Rejected</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </label>
              <div className="geometry-grid">
                <label>
                  Border
                  <select value={annotationBorder} onChange={(event) => setAnnotationBorder(event.target.value)}>
                    <option value="solid">Solid</option>
                    <option value="dashed">Dashed</option>
                    <option value="beveled">Beveled</option>
                    <option value="inset">Inset</option>
                    <option value="underline">Underline</option>
                  </select>
                </label>
                <label>
                  Width
                  <input type="number" min="0.1" max="100" step="0.5" value={annotationWidth}
                    onChange={(event) => setAnnotationWidth(Number(event.target.value))} />
                </label>
              </div>
              {annotationKind === "annotate.attachment" && (
                <label>
                  Attached vault file
                  <select value={attachmentId} onChange={(event) => setAttachmentId(event.target.value)}>
                    <option value="">Choose a file</option>
                    {files.map((asset) => (
                      <option key={asset.id} value={asset.id}>{asset.display_name}</option>
                    ))}
                  </select>
                </label>
              )}
              <small className="field-help">
                Audio annotations are {audioAnnotationsSupported ? "supported by this PDF engine" : "not available in the installed PDF engine"}.
              </small>
            </div>
          )}
          {["text", "comment", "free_text", "link", "form"].includes(tool) && (
            <label>
              {tool === "link"
                ? "Web address"
                : tool === "form"
                  ? "Field name"
                  : "Text"}
              <input
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            </label>
          )}
          {tool === "shape" && (
            <label>
              Shape
              <select
                value={shapeKind}
                onChange={(event) => setShapeKind(event.target.value)}
              >
                <option value="rectangle">Rectangle</option>
                <option value="ellipse">Ellipse</option>
                <option value="line">Line</option>
              </select>
            </label>
          )}
          {tool === "form" && (
            <label>
              Field type
              <select
                value={formKind}
                onChange={(event) => setFormKind(event.target.value)}
              >
                <option value="form.text">Text field</option>
                <option value="form.multiline">Multiline text</option>
                <option value="form.checkbox">Checkbox</option>
                <option value="form.radio">Radio button</option>
                <option value="form.combo">Combo box</option>
                <option value="form.listbox">List box</option>
                <option value="form.pushbutton">Push button</option>
                <option value="form.signature">Signature field</option>
                <option value="form.date">Date field</option>
                <option value="form.numeric">Numeric field</option>
              </select>
            </label>
          )}
          {tool === "form" && (
            <label>
              Value or comma-separated choices
              <input
                value={replacement}
                onChange={(event) => setReplacement(event.target.value)}
                placeholder={
                  ["form.radio", "form.combo", "form.listbox"].includes(formKind)
                    ? "Option 1, Option 2"
                    : "Current value"
                }
              />
            </label>
          )}
          {["text", "comment", "free_text", "form"].includes(tool) && (
            <>
              <label>
                Font
                <select
                  value={font}
                  onChange={(event) => setFont(event.target.value)}
                >
                  <option>Helvetica</option>
                  <option>Times</option>
                  <option>Courier</option>
                </select>
              </label>
              <label>
                Size
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={fontSize}
                  onChange={(event) => setFontSize(Number(event.target.value))}
                />
              </label>
            </>
          )}
          {tool !== "select" && (
            <>
              <label>
                Color
                <input
                  type="color"
                  value={color}
                  onChange={(event) => setColor(event.target.value)}
                />
              </label>
              <label>
                Fill
                <input
                  type="color"
                  value={fill}
                  onChange={(event) => setFill(event.target.value)}
                />
              </label>
              <label>
                Opacity <span>{Math.round(opacity * 100)}%</span>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={opacity}
                  onChange={(event) => setOpacity(Number(event.target.value))}
                />
              </label>
            </>
          )}
          {["image", "signature"].includes(tool) && (
            <label>
              Image asset
              <select
                value={imageId}
                onChange={(event) => setImageId(event.target.value)}
              >
                <option value="">Choose an image</option>
                {imageAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.display_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <p className="tool-hint">
            {tool === "select"
              ? "Choose a tool, set its properties, then click the page to place the edit."
              : "Click the page where this element should be placed. Pending edits are outlined until export."}
          </p>
          <div className="document-facts">
            <p className="eyebrow">PAGE INSPECTOR</p>
            <span>{pageInfo?.fonts.length || 0} fonts</span>
            <span>{pageInfo?.images || 0} images</span>
            <span>{pageInfo?.links || 0} links</span>
            <span>{pageInfo?.annotations || 0} annotations</span>
            {!!pageInfo?.subset_fonts.length && (
              <small>Subset fonts: {pageInfo.subset_fonts.join(", ")}</small>
            )}
          </div>
          <details className="comments-panel" open>
            <summary>Comments & annotations ({annotations.length})</summary>
            <div className="comment-filters">
              <input
                value={annotationSearch}
                onChange={(event) => setAnnotationSearch(event.target.value)}
                placeholder="Search comments"
              />
              <div className="geometry-grid">
                <select value={annotationPageFilter} onChange={(event) => setAnnotationPageFilter(event.target.value)}>
                  <option value="all">All pages</option>
                  <option value="current">Current page</option>
                </select>
                <select value={annotationSort} onChange={(event) => setAnnotationSort(event.target.value)}>
                  <option value="page">Page order</option>
                  <option value="newest">Newest first</option>
                  <option value="oldest">Oldest first</option>
                </select>
              </div>
              <div className="geometry-grid">
                <select value={annotationTypeFilter} onChange={(event) => setAnnotationTypeFilter(event.target.value)}>
                  <option value="">All types</option>
                  <option value="Text">Text notes</option>
                  <option value="FreeText">Text boxes</option>
                  <option value="Highlight">Highlights</option>
                  <option value="Underline">Underlines</option>
                  <option value="Squiggly">Squiggly</option>
                  <option value="StrikeOut">Strikeouts</option>
                  <option value="Ink">Ink</option>
                  <option value="Line">Lines & measurements</option>
                  <option value="Square">Rectangles</option>
                  <option value="Circle">Ellipses</option>
                  <option value="Polygon">Polygons</option>
                  <option value="PolyLine">Polylines</option>
                  <option value="Stamp">Stamps</option>
                  <option value="FileAttachment">Attachments</option>
                  <option value="Caret">Carets</option>
                  <option value="Redact">Redaction marks</option>
                </select>
                <select value={annotationStatusFilter} onChange={(event) => setAnnotationStatusFilter(event.target.value)}>
                  <option value="">All statuses</option>
                  <option value="none">No status</option>
                  <option value="open">Open</option>
                  <option value="accepted">Accepted</option>
                  <option value="rejected">Rejected</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
              <label className="checkbox-line">
                <input type="checkbox" checked={hideResolved} onChange={(event) => setHideResolved(event.target.checked)} />
                Hide resolved reviews
              </label>
            </div>
            <div className="comment-list">
              {annotations.map((annotation) => (
                <button
                  key={annotation.id}
                  className={`${selectedAnnotationId === annotation.id ? "active" : ""} ${annotation.parent_id ? "reply" : ""}`}
                  onClick={() => {
                    setSelectedAnnotationId(annotation.id);
                    setPage(annotation.page);
                    setAnnotationAuthor(annotation.author);
                    setAnnotationSubject(annotation.subject);
                    setAnnotationStatus(annotation.status);
                    setColor(annotation.color);
                    if (annotation.fill) setFill(annotation.fill);
                    setOpacity(annotation.opacity);
                    setAnnotationWidth(annotation.width);
                    setAnnotationBorder(annotation.border_style);
                    setText(annotation.comment);
                  }}
                >
                  <span>
                    <b>{annotation.author || "Anonymous"}</b>
                    <small>Page {annotation.page} · {annotation.type} · {annotation.status}</small>
                  </span>
                  <span>{annotation.comment || annotation.subject || "Annotation"}</span>
                  {!!annotation.reply_count && <small>{annotation.reply_count} replies</small>}
                </button>
              ))}
              {!annotations.length && <small>No annotations match these filters.</small>}
            </div>
            {selectedAnnotation && (
              <div className="selected-comment-editor">
                <b>Edit selected annotation</b>
                <div className="geometry-actions">
                  <button
                    disabled={busy}
                    onClick={() => updateAnnotation(selectedAnnotation, {
                      text,
                      author: annotationAuthor,
                      subject: annotationSubject,
                      annotation_status: annotationStatus,
                      color,
                      fill,
                      opacity,
                      width: annotationWidth,
                      border_style: annotationBorder,
                    })}
                  >
                    Apply properties
                  </button>
                  <button disabled={busy} onClick={() => updateAnnotation(selectedAnnotation, { locked: !selectedAnnotation.locked })}>
                    {selectedAnnotation.locked ? "Unlock" : "Lock"}
                  </button>
                  <button disabled={busy} onClick={() => updateAnnotation(selectedAnnotation, { visible: !selectedAnnotation.visible })}>
                    {selectedAnnotation.visible ? "Hide" : "Show"}
                  </button>
                  <button disabled={busy} onClick={() => updateAnnotation(selectedAnnotation, { printable: !selectedAnnotation.printable })}>
                    {selectedAnnotation.printable ? "Do not print" : "Print"}
                  </button>
                  <button disabled={busy} onClick={() => deleteAnnotation(selectedAnnotation)}>Delete</button>
                </div>
                <label>
                  Thread reply
                  <textarea value={replyText} onChange={(event) => setReplyText(event.target.value)} placeholder="Write a reply" />
                </label>
                <button className="secondary" disabled={busy || !replyText.trim()} onClick={() => replyToAnnotation(selectedAnnotation)}>
                  Add reply
                </button>
              </div>
            )}
          </details>
          <details className="content-inspector" open>
            <summary>Native text objects ({sceneText.length})</summary>
            <label>
              Replacement text
              <input
                value={replacement}
                onChange={(event) => setReplacement(event.target.value)}
                placeholder="New wording"
              />
            </label>
            <div>
              {sceneText.slice(0, 30).map((block) => (
                <button
                  key={block.id}
                  title={`${block.style.font || "Unknown font"} · ${Math.round(block.style.font_size || 0)} pt · ${block.editability}`}
                  onClick={() => {
                    setText(block.text);
                    replaceExistingText(block);
                  }}
                >
                  <span>{block.text}</span>
                  <small>
                    {block.style.font || "Unknown font"} ·{" "}
                    {Math.round(block.style.font_size || 0)} pt ·{" "}
                    {block.editability}
                  </small>
                </button>
              ))}
            </div>
          </details>
          <details className="content-inspector" open>
            <summary>Existing images ({sceneImages.length})</summary>
            <label>
              Replacement asset
              <select
                value={imageId}
                onChange={(event) => setImageId(event.target.value)}
              >
                <option value="">Choose an image</option>
                {imageAssets.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.display_name}
                  </option>
                ))}
              </select>
            </label>
            <div>
              {sceneImages.map((item, index) => (
                <div className="object-editor" key={item.id}>
                  <span>
                    Image {index + 1} ·{" "}
                    {Math.round(item.bounds[2] - item.bounds[0])} ×{" "}
                    {Math.round(item.bounds[3] - item.bounds[1])} pt
                  </span>
                  <small>{item.editability}</small>
                  <div className="object-actions">
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingImage(item, "move")}
                    >
                      Move
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingImage(item, "resize")}
                    >
                      Resize
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingImage(item, "rotate")}
                    >
                      Rotate 15°
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingImage(item, "crop")}
                    >
                      Crop 10%
                    </button>
                    <button
                      disabled={busy || item.lock_state || !imageId}
                      onClick={() => editExistingImage(item, "replace")}
                    >
                      Replace
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingImage(item, "delete")}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {!sceneImages.length && (
                <small>No raster image objects on this page.</small>
              )}
            </div>
          </details>
          <details className="content-inspector">
            <summary>Existing vector paths ({sceneVectors.length})</summary>
            <div>
              {sceneVectors.map((item, index) => (
                <div className="object-editor" key={item.id}>
                  <span>
                    Path {index + 1} · {item.properties.type || "path"}
                  </span>
                  <small>{item.editability}</small>
                  <div className="object-actions">
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingVector(item, "move")}
                    >
                      Move
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingVector(item, "resize")}
                    >
                      Resize
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingVector(item, "rotate")}
                    >
                      Rotate 15°
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingVector(item, "restyle")}
                    >
                      Apply style
                    </button>
                    <button
                      disabled={busy || item.lock_state}
                      onClick={() => editExistingVector(item, "delete")}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {!sceneVectors.length && (
                <small>No safely editable vector paths on this page.</small>
              )}
            </div>
          </details>
          <details className="document-tools">
            <summary>Bookmarks & embedded attachments</summary>
            <label>Bookmark title<input value={bookmarkTitle} onChange={(event) => setBookmarkTitle(event.target.value)} placeholder="Section title" /></label>
            <button className="secondary" disabled={busy || !bookmarkTitle} onClick={() => applyNavigationOperation({
              kind: "bookmark.add", bookmark_title: bookmarkTitle, bookmark_level: 1, target_page: page,
            } as PdfOperation)}>Add bookmark to this page</button>
            <div className="navigation-list">
              {bookmarks.map((bookmark) => <div key={`${bookmark.index}-${bookmark.title}`}>
                <button onClick={() => setPage(bookmark.page)} style={{ paddingLeft: `${bookmark.level * 8}px` }}>{bookmark.title}<small>Page {bookmark.page}</small></button>
                <button title="Delete bookmark" onClick={() => applyNavigationOperation({ kind: "bookmark.delete", bookmark_index: bookmark.index })}>×</button>
              </div>)}
            </div>
            <label>Vault file to embed<select value={attachmentAssetId} onChange={(event) => {
              setAttachmentAssetId(event.target.value); const asset = files.find((item) => item.id === event.target.value);
              if (asset) setAttachmentName(asset.display_name);
            }}><option value="">Choose a file</option>{files.map((asset) => <option key={asset.id} value={asset.id}>{asset.display_name}</option>)}</select></label>
            <label>Embedded filename<input value={attachmentName} onChange={(event) => setAttachmentName(event.target.value)} /></label>
            <button className="secondary" disabled={busy || !attachmentAssetId || !attachmentName} onClick={() => applyNavigationOperation({
              kind: "attachment.add", attachment_file_id: attachmentAssetId, attachment_name: attachmentName,
              text: `Embedded from ${attachmentName}`,
            })}>Embed file in PDF</button>
            <div className="navigation-list">
              {embeddedAttachments.map((attachment) => <div key={attachment.name}>
                <button onClick={() => downloadEmbeddedAttachment(attachment.name)}>{attachment.name}<small>{attachment.size || 0} bytes</small></button>
                <button title="Delete attachment" onClick={() => applyNavigationOperation({ kind: "attachment.delete", attachment_name: attachment.name })}>×</button>
              </div>)}
            </div>
          </details>
          <details className="document-tools comparison-studio">
            <summary>Document Comparison Studio</summary>
            <label>
              Compare current source with
              <select value={compareFileId} onChange={(event) => setCompareFileId(event.target.value)}>
                <option value="">Choose another PDF</option>
                {pdfs.filter((file) => file.id !== project.source_file_id).map((file) => (
                  <option key={file.id} value={file.id}>{file.display_name}</option>
                ))}
              </select>
            </label>
            <button className="secondary" disabled={busy || !compareFileId} onClick={compareDocuments}>Run text, object, page, and visual comparison</button>
            {comparison && (
              <>
                <div className="geometry-grid">
                  <label>View
                    <select value={comparisonMode} onChange={(event) => setComparisonMode(event.target.value)}>
                      <option value="side-by-side">Side by side</option>
                      <option value="overlay">Difference overlay</option>
                    </select>
                  </label>
                  <label>Difference type
                    <select value={comparisonFilter} onChange={(event) => setComparisonFilter(event.target.value)}>
                      <option value="">All differences</option>
                      {Object.keys(comparison.summary.by_type).sort().map((kind) => <option key={kind}>{kind}</option>)}
                    </select>
                  </label>
                </div>
                <div className={`comparison-view ${comparisonMode}`}>
                  {comparisonMode === "overlay" ? (
                    comparisonImages.overlay && <img src={comparisonImages.overlay} alt="PDF difference overlay" />
                  ) : (
                    <>{comparisonImages.before && <img src={comparisonImages.before} alt="Original PDF page" />}
                      {comparisonImages.after && <img src={comparisonImages.after} alt="Compared PDF page" />}</>
                  )}
                </div>
                <div className="comparison-differences">
                  {comparison.differences.filter((item) => !comparisonFilter || item.type === comparisonFilter).map((item) => (
                    <button key={item.id} className={item.reviewed ? "reviewed" : ""} onClick={() => {
                      setComparison((current) => current ? { ...current, differences: current.differences.map((difference) =>
                        difference.id === item.id ? { ...difference, reviewed: !difference.reviewed } : difference) } : current);
                      void loadComparisonImages(comparison.after_file_id, item.after_page || item.before_page || 1);
                    }}>
                      <span>{item.type.replaceAll("_", " ")}</span>
                      <small>Before {item.before_page || "—"} · After {item.after_page || "—"} · {item.reviewed ? "Reviewed" : "Needs review"}</small>
                    </button>
                  ))}
                </div>
                <button className="secondary" onClick={exportComparisonReport}>Export comparison report</button>
              </>
            )}
          </details>
          <details className="document-tools">
            <summary>Secure Redaction Studio</summary>
            <label>
              Search pattern
              <select value={redactionPattern} onChange={(event) => setRedactionPattern(event.target.value)}>
                <option value="keyword">Keyword list</option>
                <option value="name">Person names</option>
                <option value="email">Email addresses</option>
                <option value="phone">Phone numbers</option>
                <option value="account">Account numbers</option>
                <option value="credit_card">Credit-card patterns</option>
                <option value="national_id">National identifiers</option>
                <option value="ip">IP addresses</option>
                <option value="date">Dates</option>
                <option value="custom_regex">Custom regular expression</option>
              </select>
            </label>
            <label>
              Keywords (comma or line separated)
              <textarea value={redactionTerms} onChange={(event) => setRedactionTerms(event.target.value)} />
            </label>
            {redactionPattern === "custom_regex" && (
              <label>
                Safe regular expression
                <input value={replacement} onChange={(event) => setReplacement(event.target.value)} />
              </label>
            )}
            <label className="checkbox-line"><input type="checkbox" checked={redactionMetadata} onChange={(event) => setRedactionMetadata(event.target.checked)} />Remove metadata and XMP</label>
            <label className="checkbox-line"><input type="checkbox" checked={redactionComments} onChange={(event) => setRedactionComments(event.target.checked)} />Remove comments and replies</label>
            <label className="checkbox-line"><input type="checkbox" checked={redactionAttachments} onChange={(event) => setRedactionAttachments(event.target.checked)} />Remove embedded attachments</label>
            <label className="checkbox-line"><input type="checkbox" checked={redactionForms} onChange={(event) => setRedactionForms(event.target.checked)} />Clear form values</label>
            <small className="field-help">Underlying text, touched image pixels, hidden text, and document JavaScript are removed. The export report checks that requested keywords and custom patterns are no longer extractable.</small>
            <button className="secondary" disabled={busy} onClick={applySearchRedaction}>Review and apply search redaction</button>
          </details>
          <details className="document-tools" open>
            <summary>Page import & geometry</summary>
            <label>
              Import from PDF
              <select
                value={pageSourceId}
                onChange={(event) => setPageSourceId(event.target.value)}
              >
                <option value="">Choose a PDF</option>
                {pdfs.map((file) => (
                  <option key={file.id} value={file.id}>
                    {file.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Source page number
              <input
                type="number"
                min="1"
                value={pageSourceNumber}
                onChange={(event) =>
                  setPageSourceNumber(Math.max(1, Number(event.target.value)))
                }
              />
            </label>
            <div className="geometry-actions">
              <button
                className="secondary"
                disabled={busy || !pageSourceId}
                onClick={() => importExistingPage("insert")}
              >
                Insert after page
              </button>
              <button
                className="secondary"
                disabled={busy || !pageSourceId}
                onClick={() => importExistingPage("replace")}
              >
                Replace this page
              </button>
            </div>
            <div className="geometry-grid">
              <label>
                Page width (pt)
                <input
                  type="number"
                  min="36"
                  max="14400"
                  value={pageWidthValue}
                  onChange={(event) =>
                    setPageWidthValue(Number(event.target.value))
                  }
                />
              </label>
              <label>
                Page height (pt)
                <input
                  type="number"
                  min="36"
                  max="14400"
                  value={pageHeightValue}
                  onChange={(event) =>
                    setPageHeightValue(Number(event.target.value))
                  }
                />
              </label>
            </div>
            <label>
              Content scaling
              <select
                value={resizeMode}
                onChange={(event) => setResizeMode(event.target.value)}
              >
                <option value="fit">Fit with margins</option>
                <option value="fill">Fill and crop overflow</option>
                <option value="stretch">Stretch to page</option>
              </select>
            </label>
            <button
              className="secondary"
              disabled={busy || pageWidthValue < 36 || pageHeightValue < 36}
              onClick={() => updatePageGeometry("resize")}
            >
              Resize page and content
            </button>
            <small className="field-help">
              Box coordinates use left, top, right, bottom points.
            </small>
            {(["media", "crop", "bleed", "trim", "art"] as const).map(
              (name) => (
                <label key={name}>
                  {name[0].toUpperCase() + name.slice(1)} box
                  <input
                    value={(pageBoxes[name] || []).join(", ")}
                    onChange={(event) => updateBox(name, event.target.value)}
                  />
                </label>
              ),
            )}
            <button
              className="secondary"
              disabled={
                busy ||
                ["media", "crop", "bleed", "trim", "art"].some(
                  (name) => (pageBoxes[name] || []).length !== 4,
                )
              }
              onClick={() => updatePageGeometry("set_boxes")}
            >
              Apply all page boxes
            </button>
          </details>
          <details className="document-tools">
            <summary>Document-wide tools</summary>
            <label>
              Text or document title
              <input
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            </label>
            <button
              className="secondary"
              onClick={() => addDocumentOperation("watermark.text")}
            >
              Add watermark
            </button>
            <button
              className="secondary"
              onClick={() => addDocumentOperation("header_footer")}
            >
              Add footer / page numbers
            </button>
            <button
              className="secondary"
              onClick={() => addDocumentOperation("metadata.set")}
            >
              Set document title
            </button>
          </details>
          <details className="revision-history">
            <summary>Revision history ({revisions.length})</summary>
            {revisions.map((item) => (
              <button
                key={item.revision}
                onClick={() => restoreRevision(item.revision)}
              >
                Revision {item.revision}
                <small>{new Date(item.created_at).toLocaleString()}</small>
              </button>
            ))}
          </details>
        </aside>
      </div>
    </section>
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
            {adminCapabilities.map((capability) => (
              <label key={`${capability.engine_id}-${capability.operation}`}>
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
