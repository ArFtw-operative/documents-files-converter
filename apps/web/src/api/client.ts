/** Fetch wrapper: same-origin cookies, CSRF double-submit header, structured errors. */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }

  get isNetwork(): boolean {
    return this.status === 0;
  }
}

function cookie(name: string): string | null {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

interface Options {
  method?: string;
  json?: unknown;
  body?: BodyInit;
  signal?: AbortSignal;
}

export async function api<T = unknown>(path: string, options: Options = {}): Promise<T> {
  const method = options.method ?? (options.json !== undefined || options.body ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = cookie("folio_csrf") ?? "";
  let body = options.body;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }
  let response: Response;
  try {
    response = await fetch(path, { method, headers, body, credentials: "same-origin", signal: options.signal });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "network", "Cannot reach the server. Your changes are kept and will be retried.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (data?.error) throw new ApiError(response.status, data.error.code, data.error.message, data.error.details ?? {});
    const detail = data?.detail;
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      throw new ApiError(response.status, detail.mfa_required ? "mfa_required" : "error", detail.message ?? "Request failed.", detail);
    }
    const message = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ")
      : typeof detail === "string" ? detail : `Request failed (${response.status}).`;
    throw new ApiError(response.status, "error", message);
  }
  return data as T;
}

export function newBatchId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  return `b-${Date.now().toString(36)}-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = value / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}
