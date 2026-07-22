export const API =
  process.env.NEXT_PUBLIC_API_URL ??
  (typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000`
    : "http://localhost:8000");

let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) throw new Error("Authentication required");
    const response = await fetch(`${API}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      throw new Error("Authentication required");
    }
    const data = await response.json();
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    return data.access_token as string;
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  let response = await fetch(`${API}${path}`, { ...options, headers });
  if (
    response.status === 401 &&
    typeof window !== "undefined" &&
    localStorage.getItem("refresh_token") &&
    !path.startsWith("/api/v1/auth/")
  ) {
    const renewed = await refreshAccessToken();
    headers.set("Authorization", `Bearer ${renewed}`);
    response = await fetch(`${API}${path}`, { ...options, headers });
  }
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

export const size = (bytes: number) =>
  new Intl.NumberFormat(undefined, {
    style: "unit",
    unit: bytes > 1048576 ? "megabyte" : "kilobyte",
    maximumFractionDigits: 1,
  }).format(bytes / (bytes > 1048576 ? 1048576 : 1024));

/** Authenticated fetch that returns an object URL for a rendered/binary asset. */
export async function fetchObjectUrl(path: string): Promise<string> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  let response = await fetch(`${API}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (response.status === 401 && localStorage.getItem("refresh_token")) {
    const renewed = await refreshAccessToken();
    response = await fetch(`${API}${path}`, {
      headers: { Authorization: `Bearer ${renewed}` },
    });
  }
  if (!response.ok) throw new Error("The asset could not be loaded.");
  return URL.createObjectURL(await response.blob());
}

/** Trigger a browser download for an authenticated binary endpoint. */
export async function downloadAuthed(path: string, filename: string) {
  const url = await fetchObjectUrl(path);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
