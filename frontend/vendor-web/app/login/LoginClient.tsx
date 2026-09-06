"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPending(true);
    setError(null);
    const fd = new FormData(e.currentTarget);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          usr: fd.get("usr"),
          pwd: fd.get("pwd"),
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error || "Login failed");
      const next = searchParams.get("next") || "/";
      router.push(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <p className="muted" style={{ margin: "0 0 0.35rem", fontWeight: 700, color: "var(--brand)" }}>
          Vendor Portal
        </p>
        <h1>Sign in</h1>
        <p className="muted">Use the login ID provided by your administrator.</p>
        <form onSubmit={onSubmit} style={{ marginTop: "1.25rem" }}>
          {error ? <div className="error">{error}</div> : null}
          <div className="field" style={{ marginBottom: "1rem" }}>
            <label htmlFor="usr">Login ID / Email</label>
            <input id="usr" name="usr" required autoComplete="username" />
          </div>
          <div className="field" style={{ marginBottom: "1rem" }}>
            <label htmlFor="pwd">Password</label>
            <input id="pwd" name="pwd" type="password" required autoComplete="current-password" />
          </div>
          <button className="btn btn-primary" type="submit" disabled={pending} style={{ width: "100%" }}>
            {pending ? "Signing in…" : "Sign in to portal"}
          </button>
        </form>
      </div>
    </div>
  );
}
