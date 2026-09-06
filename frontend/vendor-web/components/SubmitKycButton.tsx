"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { submitKycAction } from "@/lib/actions";

export function SubmitKycButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onClick() {
    setPending(true);
    setError(null);
    const result = await submitKycAction();
    setPending(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    router.refresh();
  }

  return (
    <div>
      {error ? <div className="error" style={{ marginBottom: "0.5rem" }}>{error}</div> : null}
      <button className="btn btn-primary" type="button" onClick={onClick} disabled={pending}>
        {pending ? "Submitting…" : "Submit for KYC review"}
      </button>
    </div>
  );
}
