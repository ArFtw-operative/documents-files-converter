import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { api, ApiError } from "../api/client";
import { keys, type AuthState } from "../api/queries";

type Mode = "setup" | "login" | "register";

export function AuthScreen({ state }: { state: AuthState }) {
  const client = useQueryClient();
  const [mode, setMode] = useState<Mode>(state.setup_required ? "setup" : "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [totp, setTotp] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await api("/api/v1/auth/login", { json: { email, password, totp: needsTotp ? totp : undefined } });
      } else {
        await api(`/api/v1/auth/${mode}`, { json: { email, password, display_name: displayName } });
      }
      await client.invalidateQueries({ queryKey: keys.auth });
    } catch (err) {
      const e = err as ApiError;
      if (e.code === "mfa_required") {
        setNeedsTotp(true);
        setError(needsTotp ? e.message : null);
      } else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const title = { setup: "Create the administrator account", login: "Sign in", register: "Create your account" }[mode];

  return (
    <main className="min-h-full flex items-center justify-center p-4" style={{ background: "var(--canvas-bg)" }}>
      <form onSubmit={submit} className="chrome border rounded-xl w-full max-w-sm p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <span className="inline-flex size-8 items-center justify-center rounded-lg bg-[var(--color-brand-600)] text-white">
            <FileText size={18} aria-hidden />
          </span>
          <div>
            <div className="font-semibold text-[15px]">{state.app_name}</div>
            <div className="muted text-xs">Private PDF studio</div>
          </div>
        </div>
        <h1 className="text-lg font-semibold">{title}</h1>
        {mode === "setup" && (
          <p className="muted text-xs">This is the first start. The account you create here manages users and settings.</p>
        )}
        {mode !== "login" && (
          <label className="block space-y-1">
            <span className="text-xs font-medium">Name</span>
            <input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required autoComplete="name" />
          </label>
        )}
        <label className="block space-y-1">
          <span className="text-xs font-medium">Email</span>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" autoFocus />
        </label>
        <label className="block space-y-1">
          <span className="text-xs font-medium">Password</span>
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
            autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "login" ? 1 : 10} />
        </label>
        {needsTotp && (
          <label className="block space-y-1">
            <span className="text-xs font-medium">Authenticator code</span>
            <input className="input tracking-widest" inputMode="numeric" pattern="[0-9 ]*" value={totp}
              onChange={(e) => setTotp(e.target.value)} autoFocus autoComplete="one-time-code" required />
          </label>
        )}
        {error && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{error}</p>}
        <button className="btn btn-primary w-full justify-center h-9" disabled={busy}>
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>
        {mode === "login" && state.registration_open && (
          <button type="button" className="text-xs underline muted" onClick={() => setMode("register")}>Create an account</button>
        )}
        {mode === "register" && (
          <button type="button" className="text-xs underline muted" onClick={() => setMode("login")}>I already have an account</button>
        )}
      </form>
    </main>
  );
}
