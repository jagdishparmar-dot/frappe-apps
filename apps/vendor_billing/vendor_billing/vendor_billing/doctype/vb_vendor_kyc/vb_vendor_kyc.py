from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from vendor_billing.notifications import notify_kyc_verified
from vendor_billing.utils import write_audit


class VBVendorKYC(Document):
    def validate(self):
        if not self.vendor:
            frappe.throw("Vendor is required.")
        if cint(self.docstatus) == 1 and (self.kyc_status or "") != "verified":
            frappe.throw("Only verified KYC can be submitted. Use Verify to freeze the record.")
        if (
            not self.is_new()
            and (self.kyc_status or "") == "pending_verification"
            and not self.flags.in_kyc_review
        ):
            frappe.throw("KYC is under review. Use Verify or Reject — do not edit the record directly.")
        if cint(self.docstatus) == 1 and not self.flags.in_kyc_review:
            locked = (
                "pan_number",
                "company_type",
                "bank_name",
                "account_number",
                "ifsc_code",
                "beneficiary_name",
                "address",
                "kyc_status",
            )
            if any(self.has_value_changed(field) for field in locked):
                frappe.throw(
                    "Verified KYC identity and bank details can only change through an approved profile change request."
                )

    def before_submit(self):
        if (self.kyc_status or "") != "verified":
            frappe.throw("Use Verify to submit and freeze KYC. Do not submit an unverified record.")

    def on_submit(self):
        write_audit(action="kyc.freeze", entity_type="VB Vendor KYC", entity_id=self.name)

    def before_cancel(self):
        frappe.throw("Verified KYC cannot be cancelled. Use a profile change request for bank updates.")

    def on_update(self):
        if self.vendor:
            frappe.db.set_value("VB Vendor", self.vendor, "kyc_status", self.kyc_status, update_modified=False)

    def submit_for_review(self):
        if (self.kyc_status or "") == "verified" or cint(self.docstatus) == 1:
            frappe.throw("KYC is already verified.")
        if (self.kyc_status or "") == "pending_verification":
            frappe.throw("KYC is already submitted for verification.")
        self.flags.in_kyc_review = True
        self.kyc_status = "pending_verification"
        self.submitted_at = frappe.utils.now_datetime()
        self.save(ignore_permissions=True)
        write_audit(action="kyc.submit", entity_type="VB Vendor KYC", entity_id=self.name, actor_type="vendor")

    def verify(self, remarks: str | None = None):
        if (self.kyc_status or "") != "pending_verification":
            frappe.throw("Only KYC awaiting verification can be approved.")
        self.flags.in_kyc_review = True
        self.kyc_status = "verified"
        self.verified_at = frappe.utils.now_datetime()
        if remarks:
            self.remarks = remarks
        self.save(ignore_permissions=True)
        if cint(self.docstatus) == 0:
            self.flags.ignore_permissions = True
            self.submit()
        write_audit(action="kyc.verify", entity_type="VB Vendor KYC", entity_id=self.name)
        notify_kyc_verified(self.vendor)

    def reject(self, remarks: str):
        if not remarks:
            frappe.throw("Rejection remarks are required.")
        if (self.kyc_status or "") != "pending_verification":
            frappe.throw("Only KYC awaiting verification can be rejected.")
        self.flags.in_kyc_review = True
        self.append(
            "previous_rejections",
            {
                "remarks": remarks,
                "rejected_at": frappe.utils.now_datetime(),
                "rejected_by": frappe.session.user,
            },
        )
        self.kyc_status = "rejected"
        self.remarks = remarks
        self.save(ignore_permissions=True)
        write_audit(action="kyc.reject", entity_type="VB Vendor KYC", entity_id=self.name, metadata={"remarks": remarks})
