export type KycStatus =
  | "Draft"
  | "Pending Review"
  | "Under Review"
  | "Verified"
  | "Rejected";

export type DocStatus = "Pending" | "Approved" | "Rejected";

export type VendorDocument = {
  name?: string;
  idx?: number;
  document_type: string;
  attachment: string;
  status: DocStatus;
  uploaded_on?: string;
  uploaded_by?: string;
  vendor_remarks?: string;
  admin_remarks?: string;
};

export type VendorProfile = {
  name: string;
  vendor_name: string;
  vendor_code?: string;
  status: string;
  vendor_type?: string;
  email?: string;
  phone?: string;
  website?: string;
  contact_person?: string;
  address_line1?: string;
  address_line2?: string;
  city?: string;
  state?: string;
  pincode?: string;
  country?: string;
  gstin?: string;
  pan?: string;
  gst_registration_type?: string;
  place_of_supply?: string;
  bank_name?: string;
  account_holder_name?: string;
  account_number?: string;
  ifsc_code?: string;
  branch?: string;
  upi_id?: string;
  notes?: string;
  kyc_status: KycStatus;
  kyc_remarks?: string;
  kyc_reviewed_on?: string;
  kyc_documents?: VendorDocument[];
  portal_login_id?: string;
};

export const DOCUMENT_TYPES = [
  "GST Certificate",
  "PAN Card",
  "Cancelled Cheque",
  "Address Proof",
  "Bank Statement",
  "Other",
] as const;

export type ProfileUpdate = Partial<
  Pick<
    VendorProfile,
    | "vendor_name"
    | "contact_person"
    | "email"
    | "phone"
    | "website"
    | "address_line1"
    | "address_line2"
    | "city"
    | "state"
    | "pincode"
    | "country"
    | "gstin"
    | "pan"
    | "gst_registration_type"
    | "place_of_supply"
    | "bank_name"
    | "account_holder_name"
    | "account_number"
    | "ifsc_code"
    | "branch"
    | "upi_id"
    | "notes"
  >
>;
