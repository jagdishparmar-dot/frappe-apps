"use client";

import { useActionState } from "react";
import type { VendorProfile } from "@/lib/types";
import { updateProfileAction, type ActionState } from "@/lib/actions";

function Field({
  name,
  label,
  defaultValue,
  as,
  options,
  required,
}: {
  name: string;
  label: string;
  defaultValue?: string;
  as?: "select" | "textarea";
  options?: string[];
  required?: boolean;
}) {
  return (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      {as === "select" ? (
        <select id={name} name={name} defaultValue={defaultValue || ""} required={required}>
          {options?.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : as === "textarea" ? (
        <textarea id={name} name={name} defaultValue={defaultValue || ""} />
      ) : (
        <input id={name} name={name} defaultValue={defaultValue || ""} required={required} />
      )}
    </div>
  );
}

export function ProfileForm({ vendor }: { vendor: VendorProfile }) {
  const [state, action, pending] = useActionState(updateProfileAction, {} as ActionState);

  return (
    <form action={action}>
      {state.error ? <div className="error">{state.error}</div> : null}
      {state.ok ? <div className="success">{state.message || "Saved."}</div> : null}

      <h3 className="section-title" style={{ marginTop: 0 }}>
        Basic
      </h3>
      <div className="grid-2">
        <Field name="vendor_name" label="Vendor name" defaultValue={vendor.vendor_name} required />
        <Field name="contact_person" label="Contact person" defaultValue={vendor.contact_person} />
        <Field name="email" label="Email" defaultValue={vendor.email} />
        <Field name="phone" label="Phone" defaultValue={vendor.phone} />
        <Field name="website" label="Website" defaultValue={vendor.website} />
      </div>

      <h3 className="section-title">Address</h3>
      <div className="grid-2">
        <Field name="address_line1" label="Address line 1" defaultValue={vendor.address_line1} />
        <Field name="address_line2" label="Address line 2" defaultValue={vendor.address_line2} />
        <Field name="city" label="City" defaultValue={vendor.city} />
        <Field name="state" label="State" defaultValue={vendor.state} />
        <Field name="pincode" label="Pincode" defaultValue={vendor.pincode} />
        <Field name="country" label="Country" defaultValue={vendor.country || "India"} />
      </div>

      <h3 className="section-title">GST / Tax</h3>
      <div className="grid-2">
        <Field name="gstin" label="GSTIN" defaultValue={vendor.gstin} />
        <Field name="pan" label="PAN" defaultValue={vendor.pan} />
        <Field
          name="gst_registration_type"
          label="GST registration"
          as="select"
          options={["Regular", "Composition", "Unregistered"]}
          defaultValue={vendor.gst_registration_type || "Regular"}
        />
        <Field
          name="place_of_supply"
          label="Place of supply"
          defaultValue={vendor.place_of_supply}
        />
      </div>

      <h3 className="section-title">Bank</h3>
      <div className="grid-2">
        <Field name="bank_name" label="Bank name" defaultValue={vendor.bank_name} />
        <Field
          name="account_holder_name"
          label="Account holder"
          defaultValue={vendor.account_holder_name}
        />
        <Field name="account_number" label="Account number" defaultValue={vendor.account_number} />
        <Field name="ifsc_code" label="IFSC" defaultValue={vendor.ifsc_code} />
        <Field name="branch" label="Branch" defaultValue={vendor.branch} />
        <Field name="upi_id" label="UPI ID" defaultValue={vendor.upi_id} />
      </div>

      <h3 className="section-title">Notes</h3>
      <Field name="notes" label="Notes" as="textarea" defaultValue={vendor.notes} />

      <div style={{ marginTop: "1.25rem" }}>
        <button className="btn btn-primary" type="submit" disabled={pending}>
          {pending ? "Saving…" : "Save profile"}
        </button>
      </div>
    </form>
  );
}
