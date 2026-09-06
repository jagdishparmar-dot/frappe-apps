import { getMyVendor } from "@/lib/frappe";
import { DocumentUploadForm } from "@/components/DocumentUploadForm";
import { DocBadge, KycBadge } from "@/components/StatusBadge";
import { SubmitKycButton } from "@/components/SubmitKycButton";

export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  let vendor;
  try {
    vendor = await getMyVendor();
  } catch (err) {
    return (
      <div className="card error">
        {err instanceof Error ? err.message : "Unable to load documents."}
      </div>
    );
  }

  const docs = vendor.kyc_documents || [];

  return (
    <div>
      <div className="portal-top">
        <div>
          <h1 style={{ margin: "0 0 0.35rem", fontSize: "1.75rem" }}>KYC Documents</h1>
          <p className="muted" style={{ margin: 0 }}>
            Upload certificates and proofs for admin verification.
          </p>
        </div>
        <KycBadge status={vendor.kyc_status} />
      </div>

      <div className="status-hero">
        <section className="card">
          <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>Upload document</h2>
          <DocumentUploadForm />
        </section>
        <section className="card">
          <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>Submit for review</h2>
          <p className="muted">
            After uploading required documents, submit your KYC pack for administrator review.
          </p>
          {(vendor.kyc_status === "Draft" || vendor.kyc_status === "Rejected") && (
            <SubmitKycButton />
          )}
          {vendor.kyc_status === "Pending Review" || vendor.kyc_status === "Under Review" ? (
            <p className="muted">Your pack is already with the admin team.</p>
          ) : null}
          {vendor.kyc_status === "Verified" ? (
            <p className="muted">KYC verified. Upload again only if details change.</p>
          ) : null}
        </section>
      </div>

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>Uploaded files</h2>
        {!docs.length ? (
          <p className="muted">No documents yet.</p>
        ) : (
          docs.map((doc, i) => (
            <div className="doc-row" key={doc.name || `${doc.document_type}-${i}`}>
              <div>
                <strong>{doc.document_type}</strong>
                <div className="muted" style={{ fontSize: "0.85rem" }}>
                  {doc.vendor_remarks || doc.uploaded_on || "—"}
                </div>
                {doc.admin_remarks ? (
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    Admin: {doc.admin_remarks}
                  </div>
                ) : null}
              </div>
              <DocBadge status={doc.status} />
              <a
                className="btn btn-ghost"
                href={`/api/files?path=${encodeURIComponent(doc.attachment)}`}
                target="_blank"
                rel="noreferrer"
              >
                View
              </a>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
