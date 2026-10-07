import { lazy, Suspense, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, FolderOpen, LogOut, Settings, Shield } from "lucide-react";
import { api } from "./api/client";
import { keys, useAuthState, type SessionUser } from "./api/queries";
import { AuthScreen } from "./auth/AuthScreen";
import { LibraryPage } from "./library/LibraryPage";
import { navigate, useRoute } from "./router";

const EditorPage = lazy(() => import("./editor/EditorPage"));
const AdminPage = lazy(() => import("./admin/AdminPage"));
const AccountPage = lazy(() => import("./account/AccountPage"));

function Loading() {
  return <div className="h-full flex items-center justify-center muted">Loading…</div>;
}

export function App() {
  const auth = useAuthState();
  const route = useRoute();
  if (auth.isLoading) return <Loading />;
  if (auth.isError || !auth.data) {
    return <div className="h-full flex items-center justify-center">The server is not reachable. Retrying…</div>;
  }
  if (!auth.data.user) return <AuthScreen state={auth.data} />;
  const user = auth.data.user;

  // When a document is open, the editor owns the whole viewport (§4.2).
  if (route.name === "editor") {
    return (
      <Suspense fallback={<Loading />}>
        <EditorPage documentId={route.documentId} user={user} />
      </Suspense>
    );
  }
  return (
    <Shell user={user} active={route.name}>
      <Suspense fallback={<Loading />}>
        {route.name === "admin" && user.role === "admin" ? <AdminPage self={user} />
          : route.name === "account" ? <AccountPage user={user} />
          : <LibraryPage user={user} />}
      </Suspense>
    </Shell>
  );
}

function Shell({ user, active, children }: { user: SessionUser; active: string; children: ReactNode }) {
  const client = useQueryClient();
  const items = [
    { name: "library", label: "Library", icon: FolderOpen, path: "/" },
    ...(user.role === "admin" ? [{ name: "admin", label: "Admin", icon: Shield, path: "/admin" }] : []),
    { name: "account", label: "Account", icon: Settings, path: "/account" },
  ];
  async function logout() {
    await api("/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    client.clear();
    await client.invalidateQueries({ queryKey: keys.auth });
    navigate("/", true);
  }
  return (
    <div className="h-full flex flex-col md:flex-row">
      <nav className="chrome md:border-r border-b md:border-b-0 md:w-56 shrink-0 flex md:flex-col gap-1 p-3" aria-label="Main">
        <div className="flex items-center gap-2 px-2 pb-3 md:pb-4 mr-3 md:mr-0">
          <span className="inline-flex size-7 items-center justify-center rounded-md bg-[var(--color-brand-600)] text-white">
            <FileText size={16} aria-hidden />
          </span>
          <span className="font-semibold hidden sm:inline">Verso Folio</span>
        </div>
        {items.map(({ name, label, icon: Icon, path }) => (
          <button key={name} className="icon-btn !w-auto !justify-start gap-2 px-2 md:w-full" data-active={active === name}
            onClick={() => navigate(path)} aria-current={active === name ? "page" : undefined}>
            <Icon size={16} aria-hidden /> <span>{label}</span>
          </button>
        ))}
        <div className="md:mt-auto ml-auto md:ml-0 flex md:flex-col gap-1">
          <div className="hidden md:block px-2 pt-3 text-xs muted truncate" title={user.email}>{user.display_name}</div>
          <button className="icon-btn !w-auto !justify-start gap-2 px-2" onClick={logout}>
            <LogOut size={16} aria-hidden /> <span className="hidden sm:inline">Sign out</span>
          </button>
        </div>
      </nav>
      <main className="flex-1 min-w-0 overflow-auto">{children}</main>
    </div>
  );
}
