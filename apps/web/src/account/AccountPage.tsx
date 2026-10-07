import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { api, ApiError } from "../api/client";
import { keys, type SessionUser } from "../api/queries";

export default function AccountPage({ user }: { user: SessionUser }) {
  return (
    <div className="max-w-2xl mx-auto p-4 md:p-8 space-y-8">
      <header>
        <h1 className="text-xl font-semibold">Account</h1>
        <p className="muted text-xs">{user.display_name} · {user.email}</p>
      </header>
      {user.must_change_password && (
        <p role="alert" className="rounded-md p-3 bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          Your password was set by an administrator. Please choose your own password.
        </p>
      )}
      <PasswordForm />
      <TwoStep user={user} />
    </div>
  );
}

function PasswordForm() {
  const client = useQueryClient();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/api/v1/auth/password", { json: { current_password: current, new_password: next } });
      setCurrent("");
      setNext("");
      setMessage({ ok: true, text: "Password changed. Other sessions were signed out." });
      client.invalidateQueries({ queryKey: keys.auth });
    } catch (e) {
      setMessage({ ok: false, text: (e as ApiError).message });
    }
  }
  return (
    <form onSubmit={submit} className="chrome border rounded-xl p-4 space-y-3">
      <h2 className="font-semibold">Password</h2>
      <label className="block space-y-1"><span className="text-xs">Current password</span>
        <input className="input" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
      <label className="block space-y-1"><span className="text-xs">New password (at least 10 characters)</span>
        <input className="input" type="password" autoComplete="new-password" minLength={10} required value={next} onChange={(e) => setNext(e.target.value)} /></label>
      {message && <p role="status" className={message.ok ? "text-[var(--color-brand-600)]" : "text-red-700 dark:text-red-400"}>{message.text}</p>}
      <button className="btn btn-primary">Change password</button>
    </form>
  );
}

function TwoStep({ user }: { user: SessionUser }) {
  const client = useQueryClient();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (setup) QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 180 }).then(setQr).catch(() => setQr(null));
  }, [setup]);

  async function run(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as ApiError).message);
    }
  }

  return (
    <section className="chrome border rounded-xl p-4 space-y-3">
      <h2 className="font-semibold">Two-step sign-in</h2>
      {user.mfa_enabled ? (
        <>
          <p className="muted">On. Sign-in asks for a code from your authenticator app.</p>
          <div className="grid gap-2 sm:grid-cols-3 items-end">
            <input className="input" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
            <input className="input" inputMode="numeric" placeholder="Code" value={code} onChange={(e) => setCode(e.target.value)} />
            <button className="btn" onClick={() => run(async () => {
              await api("/api/v1/auth/mfa/disable", { json: { code, password } });
              await client.invalidateQueries({ queryKey: keys.auth });
            })}>Turn off</button>
          </div>
        </>
      ) : setup ? (
        <>
          <p className="muted">Scan with an authenticator app, then enter the 6-digit code.</p>
          {qr && <img src={qr} alt="Authenticator QR code" width={180} height={180} className="rounded bg-white p-1" />}
          <p className="text-xs muted break-all">Key: {setup.secret}</p>
          <div className="flex gap-2">
            <input className="input !w-40" inputMode="numeric" placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
            <button className="btn btn-primary" onClick={() => run(async () => {
              await api("/api/v1/auth/mfa/enable", { json: { code } });
              setSetup(null);
              setCode("");
              await client.invalidateQueries({ queryKey: keys.auth });
            })}>Turn on</button>
          </div>
        </>
      ) : (
        <button className="btn" onClick={() => run(async () => setSetup(await api("/api/v1/auth/mfa/setup", { method: "POST" })))}>
          Set up two-step sign-in
        </button>
      )}
      {error && <p role="alert" className="text-red-700 dark:text-red-400">{error}</p>}
    </section>
  );
}
