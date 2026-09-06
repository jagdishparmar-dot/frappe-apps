"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function logout() {
    setPending(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      className="btn btn-ghost"
      type="button"
      onClick={logout}
      disabled={pending}
      style={{
        width: "100%",
        borderColor: "rgba(255,255,255,0.25)",
        color: "rgba(232,242,236,0.95)",
      }}
    >
      {pending ? "Signing out…" : "Sign out"}
    </button>
  );
}
