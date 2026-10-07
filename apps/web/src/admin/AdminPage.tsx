import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { api, ApiError, formatBytes } from "../api/client";
import type { SessionUser } from "../api/queries";

interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "user";
  is_active: boolean;
  mfa_enabled: boolean;
  quota_bytes: number;
  used_bytes: number;
  documents: number;
  created_at: string;
  last_login_at: string | null;
}

interface AuditRow {
  id: string;
  at: string;
  actor_id: string | null;
  action: string;
  document_id: string | null;
  ip: string | null;
  details: Record<string, unknown>;
}

const GB = 1024 ** 3;

export default function AdminPage({ self }: { self: SessionUser }) {
  const client = useQueryClient();
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: () => api<AdminUser[]>("/api/v1/admin/users") });
  const settings = useQuery({
    queryKey: ["admin", "settings"],
    queryFn: () => api<{ registration_open: boolean; audit_privacy_mode: boolean }>("/api/v1/admin/settings"),
  });
  const audit = useQuery({ queryKey: ["admin", "audit"], queryFn: () => api<AuditRow[]>("/api/v1/admin/audit?limit=100") });
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api(`/api/v1/admin/users/${id}`, { method: "PATCH", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin"] }),
    onError: (e) => setError((e as ApiError).message),
  });
  const saveSettings = useMutation({
    mutationFn: (body: Record<string, boolean>) => api("/api/v1/admin/settings", { method: "PATCH", json: body }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin", "settings"] }),
  });
  const names = new Map(users.data?.map((u) => [u.id, u.display_name]) ?? []);

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-8 space-y-8">
      <header>
        <h1 className="text-xl font-semibold">Administration</h1>
        <p className="muted text-xs">Each person sees only their own documents. Administrators manage accounts, not content.</p>
      </header>
      {error && <p role="alert" className="text-red-700 dark:text-red-400">{error}</p>}

      <section className="space-y-3">
        <h2 className="font-semibold">Users</h2>
        <NewUserForm onCreated={() => client.invalidateQueries({ queryKey: ["admin", "users"] })} />
        <div className="chrome border rounded-xl overflow-x-auto">
          <table className="w-full text-left">
            <thead className="muted text-xs">
              <tr className="border-b border-[var(--chrome-border)]">
                <th className="p-3">Name</th><th className="p-3">Role</th><th className="p-3">Storage</th>
                <th className="p-3">Last sign-in</th><th className="p-3">Status</th><th className="p-3" />
              </tr>
            </thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id} className="border-b border-[var(--chrome-border)] last:border-0">
                  <td className="p-3"><div className="font-medium">{u.display_name}</div><div className="muted text-xs">{u.email}</div></td>
                  <td className="p-3">
                    <select className="input !h-7 !w-24" value={u.role} disabled={u.id === self.id}
                      onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value } })} aria-label={`Role of ${u.display_name}`}>
                      <option value="user">User</option><option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="p-3 whitespace-nowrap">
                    {formatBytes(u.used_bytes)} of{" "}
                    <select className="input !h-7 !w-20 inline" value={Math.round(u.quota_bytes / GB)} aria-label={`Quota of ${u.display_name}`}
                      onChange={(e) => update.mutate({ id: u.id, body: { quota_bytes: Number(e.target.value) * GB } })}>
                      {[1, 5, 10, 25, 50, 100, 250, 500].map((g) => <option key={g} value={g}>{g} GB</option>)}
                    </select>
                    <div className="muted text-xs">{u.documents} documents</div>
                  </td>
                  <td className="p-3 text-xs muted">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}</td>
                  <td className="p-3 text-xs">{u.is_active ? "Active" : "Disabled"}{u.mfa_enabled && " · 2-step"}</td>
                  <td className="p-3 text-right whitespace-nowrap space-x-1">
                    <button className="btn !h-7" onClick={() => {
                      const password = window.prompt(`New temporary password for ${u.display_name} (at least 10 characters). They will be asked to change it.`);
                      if (password) update.mutate({ id: u.id, body: { new_password: password } });
                    }}>Reset password</button>
                    {u.mfa_enabled && <button className="btn !h-7" onClick={() => window.confirm("Turn off two-step sign-in for this account?") && update.mutate({ id: u.id, body: { reset_mfa: true } })}>Reset 2-step</button>}
                    {u.id !== self.id && (
                      <button className="btn !h-7" onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>
                        {u.is_active ? "Disable" : "Enable"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">Settings</h2>
        {settings.data && (
          <div className="chrome border rounded-xl p-4 space-y-3">
            <label className="flex items-center gap-3">
              <input type="checkbox" checked={settings.data.registration_open}
                onChange={(e) => saveSettings.mutate({ registration_open: e.target.checked })} />
              <span>Allow people to create their own accounts <span className="muted text-xs">(otherwise only administrators create accounts)</span></span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" checked={settings.data.audit_privacy_mode}
                onChange={(e) => saveSettings.mutate({ audit_privacy_mode: e.target.checked })} />
              <span>Privacy mode for the audit log <span className="muted text-xs">(do not record old and new text values)</span></span>
            </label>
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-semibold">Recent activity</h2>
        <div className="chrome border rounded-xl divide-y divide-[var(--chrome-border)] text-xs">
          {audit.data?.map((row) => (
            <div key={row.id} className="px-4 py-2 flex flex-wrap gap-x-3">
              <span className="muted tabular-nums">{new Date(row.at).toLocaleString()}</span>
              <span className="font-medium">{row.actor_id ? names.get(row.actor_id) ?? "Unknown user" : "—"}</span>
              <span>{row.action}</span>
              {"old_text" in row.details && <span className="muted">“{String(row.details.old_text)}” → “{String(row.details.new_text)}”</span>}
              {"revision_after" in row.details && <span className="muted">v{String(row.details.revision_before)} → v{String(row.details.revision_after)}</span>}
              {row.ip && <span className="muted ml-auto">{row.ip}</span>}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function NewUserForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ email: "", display_name: "", password: "", role: "user" });
  const [error, setError] = useState<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api("/api/v1/admin/users", { json: form });
      setForm({ email: "", display_name: "", password: "", role: "user" });
      setOpen(false);
      onCreated();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }
  if (!open) return <button className="btn" onClick={() => setOpen(true)}><UserPlus size={15} aria-hidden /> Add user</button>;
  return (
    <form onSubmit={submit} className="chrome border rounded-xl p-4 grid gap-3 md:grid-cols-5 items-end">
      <label className="space-y-1"><span className="text-xs">Name</span>
        <input className="input" required value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></label>
      <label className="space-y-1"><span className="text-xs">Email</span>
        <input className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
      <label className="space-y-1"><span className="text-xs">Temporary password</span>
        <input className="input" required minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
      <label className="space-y-1"><span className="text-xs">Role</span>
        <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
          <option value="user">User</option><option value="admin">Admin</option>
        </select></label>
      <div className="flex gap-2"><button className="btn btn-primary">Create</button><button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button></div>
      {error && <p role="alert" className="md:col-span-5 text-red-700 dark:text-red-400">{error}</p>}
    </form>
  );
}
