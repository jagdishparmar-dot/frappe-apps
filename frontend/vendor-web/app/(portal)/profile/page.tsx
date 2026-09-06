import { getMyVendor } from "@/lib/frappe";
import { ProfileForm } from "@/components/ProfileForm";
import { KycBadge } from "@/components/StatusBadge";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  let vendor;
  try {
    vendor = await getMyVendor();
  } catch (err) {
    return (
      <div className="card error">
        {err instanceof Error ? err.message : "Unable to load profile."}
      </div>
    );
  }

  return (
    <div>
      <div className="portal-top">
        <div>
          <h1 style={{ margin: "0 0 0.35rem", fontSize: "1.75rem" }}>My Profile</h1>
          <p className="muted" style={{ margin: 0 }}>
            Keep your business, tax, and bank details up to date.
          </p>
        </div>
        <KycBadge status={vendor.kyc_status} />
      </div>
      <div className="card">
        <ProfileForm vendor={vendor} />
      </div>
    </div>
  );
}
