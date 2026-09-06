"use server";

import { revalidatePath } from "next/cache";
import {
  submitForKycReview,
  updateMyVendor,
  uploadFile,
  uploadKycDocument,
} from "@/lib/frappe";
import type { ProfileUpdate } from "@/lib/types";

export type ActionState = { error?: string; ok?: boolean; message?: string };

function formToProfile(formData: FormData): ProfileUpdate {
  const str = (key: string) => (formData.get(key)?.toString() || "").trim();
  return {
    vendor_name: str("vendor_name") || undefined,
    contact_person: str("contact_person") || undefined,
    email: str("email") || undefined,
    phone: str("phone") || undefined,
    website: str("website") || undefined,
    address_line1: str("address_line1") || undefined,
    address_line2: str("address_line2") || undefined,
    city: str("city") || undefined,
    state: str("state") || undefined,
    pincode: str("pincode") || undefined,
    country: str("country") || undefined,
    gstin: str("gstin") || undefined,
    pan: str("pan") || undefined,
    gst_registration_type: str("gst_registration_type") || undefined,
    place_of_supply: str("place_of_supply") || undefined,
    bank_name: str("bank_name") || undefined,
    account_holder_name: str("account_holder_name") || undefined,
    account_number: str("account_number") || undefined,
    ifsc_code: str("ifsc_code") || undefined,
    branch: str("branch") || undefined,
    upi_id: str("upi_id") || undefined,
    notes: str("notes") || undefined,
  };
}

export async function updateProfileAction(
  _prev: ActionState,
  formData: FormData
): Promise<ActionState> {
  try {
    const payload = formToProfile(formData);
    if (!payload.vendor_name) return { error: "Vendor name is required." };
    await updateMyVendor(payload);
    revalidatePath("/");
    revalidatePath("/profile");
    return { ok: true, message: "Profile saved." };
  } catch (err) {
    return { error: err instanceof Error ? err.message : "Failed to save profile." };
  }
}

export async function submitKycAction(): Promise<ActionState> {
  try {
    await submitForKycReview();
    revalidatePath("/");
    revalidatePath("/documents");
    return { ok: true, message: "Submitted for KYC review." };
  } catch (err) {
    return { error: err instanceof Error ? err.message : "Submit failed." };
  }
}

export async function uploadDocumentAction(
  _prev: ActionState,
  formData: FormData
): Promise<ActionState> {
  try {
    const documentType = formData.get("document_type")?.toString();
    const remarks = formData.get("vendor_remarks")?.toString() || undefined;
    const file = formData.get("file");
    if (!documentType) return { error: "Select a document type." };
    if (!(file instanceof File) || file.size === 0) {
      return { error: "Choose a file to upload." };
    }

    // Convert File in server action — in Node 22 File from formData works
    const fileUrl = await uploadFile(file);
    await uploadKycDocument({
      document_type: documentType,
      file_url: fileUrl,
      vendor_remarks: remarks,
    });
    revalidatePath("/");
    revalidatePath("/documents");
    return { ok: true, message: "Document uploaded." };
  } catch (err) {
    return { error: err instanceof Error ? err.message : "Upload failed." };
  }
}
