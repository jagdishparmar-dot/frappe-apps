from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from vendor_billing.identity import find_vendor_duplicate
from vendor_billing.notifications import notify_vendor_registered
from vendor_billing.utils import new_portal_token, normalize_phone, write_audit


class VBVendorRegistrationRequest(Document):
    def validate(self):
        self.phone_normalized = normalize_phone(self.phone)
        if not self.phone_normalized or len(self.phone_normalized) != 10:
            frappe.throw("Enter a valid 10-digit mobile number.")
        if (self.status or "pending") == "pending":
            dup = find_vendor_duplicate(self.phone_normalized, self.email, self.gst_number)
            if dup:
                frappe.throw(f"A vendor with this phone or email already exists ({dup}).")

    def before_submit(self):
        if (self.status or "pending") not in ("pending", "approved"):
            frappe.throw("Only pending registration requests can be submitted.")

    def on_update_after_submit(self):
        if self.has_value_changed("status") and self.status == "approved" and not self.vendor:
            self._create_vendor()

    def before_cancel(self):
        if (self.status or "") == "approved":
            frappe.throw("Approved registrations cannot be cancelled. Archive the vendor instead.")

    def on_cancel(self):
        write_audit(action="registration.cancel", entity_type="VB Vendor Registration Request", entity_id=self.name)

    def _create_vendor(self):
        vendor = frappe.get_doc(
            {
                "doctype": "VB Vendor",
                "vendor_name": self.applicant_name,
                "email": self.email,
                "phone": self.phone,
                "gst_number": self.gst_number,
                "token": new_portal_token(),
                "kyc_status": "pending_submission",
                "hubs": [],
                "categories": [{"billing_category": row.billing_category} for row in self.categories],
                "states": [{"state": row.state} for row in self.states],
            }
        )
        vendor.insert(ignore_permissions=True)
        self.db_set("vendor", vendor.name)
        self.db_set("reviewed_by", frappe.session.user)
        self.db_set("reviewed_at", frappe.utils.now_datetime())
        write_audit(
            action="registration.approve",
            entity_type="VB Vendor Registration Request",
            entity_id=self.name,
            metadata={"vendor": vendor.name},
        )
        notify_vendor_registered(vendor)

    def on_update(self):
        if cint(self.docstatus) != 0:
            return
        if self.has_value_changed("status") and self.status == "approved" and not self.vendor:
            self._create_vendor()
