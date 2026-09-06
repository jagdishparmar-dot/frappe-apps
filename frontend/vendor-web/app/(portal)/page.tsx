import Link from "next/link";
import { getMyVendor } from "@/lib/frappe";
import { KycBadge, DocBadge } from "@/components/StatusBadge";
import { SubmitKycButton } from "@/components/SubmitKycButton";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let vendor = null;
  let error: string | null = null;
  try {
    vendor = await getMyVendor();
  } catch (err) {
    error = err instanceof Error ? err.message : "Unable to load your vendor profile.";
  }

  if (error || !vendor) {
    return (
      <div className="card">
        <div className="error">{error || "Profile not found."}</div>
        <p className="muted">
          Your login must be linked to a Vendor by an administrator in Frappe Desk
          (Vendor → Create Portal User).
        </p>
      </div>
    );
  }

  const docs = vendor.kyc_documents || [];
  const pendingDocs = docs.filter((d) => d.status === "Pending").length;

  return (
    <div>
      <div className="portal-top">
        <div>
          <h1 style={{ margin: "0 0 0.35rem", fontSize: "1.75rem" }}>Welcome, {vendor.vendor_name}</h1>
          <p className="muted" style={{ margin: 0 }}>
            Vendor ID {vendor.name}
            {vendor.vendor_code ? ` · ${vendor.vendor_code}` : ""}
          </p>
        </div>
        <KycBadge status={vendor.kyc_status} />
      </div>

      <div className="status-hero">
        <section className="card">
          <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>KYC status</h2>
          <p className="muted">
            {vendor.kyc_status === "Verified" &&
              "Your KYC is verified. Keep documents up to date if your tax or bank details change."}
            {vendor.kyc_status === "Pending Review" &&
              "Your submission is waiting for admin review."}
            {vendor.kyc_status === "Under Review" &&
              "An administrator is currently reviewing your documents."}
            {vendor.kyc_status === "Rejected" &&
              (vendor.kyc_remarks ||
                "Your KYC was rejected. Update documents and resubmit.")}
            {vendor.kyc_status === "Draft" &&
              "Complete your profile, upload KYC documents, then submit for review."}
          </p>
          {vendor.kyc_remarks && vendor.kyc_status !== "Rejected" ? (
            <p>
              <strong>Admin note:</strong> {vendor.kyc_remarks}
            </p>
          ) : null}
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", marginTop: "1rem" }}>
            <Link className="btn btn-ghost" href="/profile">
              Edit profile
            </Link>
            <Link className="btn btn-ghost" href="/documents">
              Manage documents
            </Link>
            {(vendor.kyc_status === "Draft" || vendor.kyc_status === "Rejected") && (
              <SubmitKycButton />
            )}
          </div>
        </section>

        <section className="card">
          <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>At a glance</h2>
          <dl style={{ display: "grid", gap: "0.65rem", margin: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
              <dt className="muted">Documents</dt>
              <dd style={{ margin: 0 }}>{docs.length}</dd>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
              <dt className="muted">Pending review</dt>
              <dd style={{ margin: 0 }}>{pendingDocs}</dd>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
              <dt className="muted">City</dt>
              <dd style={{ margin: 0 }}>{vendor.city || "—"}</dd>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
              <dt className="muted">GSTIN</dt>
              <dd style={{ margin: 0 }}>{vendor.gstin || "—"}</dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="card" style={{ marginTop: "1rem" }}>
        <h2 style={{ marginTop: 0, fontSize: "1.1rem" }}>Recent documents</h2>
        {!docs.length ? (
          <p className="muted">No documents uploaded yet.</p>
        ) : (
          docs.slice(-5).reverse().map((doc, i) => (
            <div className="doc-row" key={doc.name || `${doc.document_type}-${i}`}>
              <div>
                <strong>{doc.document_type}</strong>
                <div className="muted" style={{ fontSize: "0.85rem" }}>
                  {doc.uploaded_on || "—"}
                </div>
              </div>
              <DocBadge status={doc.status} />
              <a className="btn btn-ghost" href={doc.attachment} target="_blank" rel="noreferrer">
                View
              </a>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
