"use client";

import { useActionState } from "react";
import { DOCUMENT_TYPES } from "@/lib/types";
import { uploadDocumentAction, type ActionState } from "@/lib/actions";

export function DocumentUploadForm() {
  const [state, action, pending] = useActionState(uploadDocumentAction, {} as ActionState);

  return (
    <form action={action}>
      {state.error ? <div className="error">{state.error}</div> : null}
      {state.ok ? <div className="success">{state.message || "Uploaded."}</div> : null}

      <div className="field" style={{ marginBottom: "0.85rem" }}>
        <label htmlFor="document_type">Document type</label>
        <select id="document_type" name="document_type" required defaultValue="">
          <option value="" disabled>
            Select type
          </option>
          {DOCUMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="field" style={{ marginBottom: "0.85rem" }}>
        <label htmlFor="file">File</label>
        <input id="file" name="file" type="file" required accept=".pdf,.jpg,.jpeg,.png,.webp" />
      </div>

      <div className="field" style={{ marginBottom: "1rem" }}>
        <label htmlFor="vendor_remarks">Remarks (optional)</label>
        <textarea id="vendor_remarks" name="vendor_remarks" />
      </div>

      <button className="btn btn-primary" type="submit" disabled={pending}>
        {pending ? "Uploading…" : "Upload document"}
      </button>
    </form>
  );
}
