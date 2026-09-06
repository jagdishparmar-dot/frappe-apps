import type { KycStatus, DocStatus } from "@/lib/types";

export function kycBadgeClass(status?: KycStatus | string) {
  switch (status) {
    case "Verified":
      return "badge badge-verified";
    case "Rejected":
      return "badge badge-rejected";
    case "Under Review":
      return "badge badge-review";
    case "Pending Review":
      return "badge badge-pending";
    default:
      return "badge badge-draft";
  }
}

export function docBadgeClass(status?: DocStatus | string) {
  switch (status) {
    case "Approved":
      return "badge badge-verified";
    case "Rejected":
      return "badge badge-rejected";
    default:
      return "badge badge-pending";
  }
}

export function KycBadge({ status }: { status?: string }) {
  return <span className={kycBadgeClass(status)}>{status || "Draft"}</span>;
}

export function DocBadge({ status }: { status?: string }) {
  return <span className={docBadgeClass(status)}>{status || "Pending"}</span>;
}
