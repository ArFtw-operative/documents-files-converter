import { useSyncExternalStore } from "react";

/** Minimal history router: "/", "/d/:id", "/admin", "/account". */

export type Route =
  | { name: "library" }
  | { name: "editor"; documentId: string }
  | { name: "admin" }
  | { name: "account" };

function parse(pathname: string): Route {
  const editor = pathname.match(/^\/d\/([0-9a-f-]{36})\/?$/);
  if (editor) return { name: "editor", documentId: editor[1] };
  if (pathname.startsWith("/admin")) return { name: "admin" };
  if (pathname.startsWith("/account")) return { name: "account" };
  return { name: "library" };
}

const listeners = new Set<() => void>();
window.addEventListener("popstate", () => listeners.forEach((l) => l()));

export function navigate(path: string, replace = false): void {
  if (path === window.location.pathname) return;
  if (replace) window.history.replaceState(null, "", path);
  else window.history.pushState(null, "", path);
  listeners.forEach((l) => l());
}

export function useRoute(): Route {
  const pathname = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => window.location.pathname,
  );
  return parse(pathname);
}
