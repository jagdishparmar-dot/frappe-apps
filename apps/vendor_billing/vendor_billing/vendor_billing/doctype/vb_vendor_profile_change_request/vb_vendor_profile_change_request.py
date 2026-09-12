from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from vendor_billing.utils import write_audit


class VBVendorProfileChangeRequest(Document):
    def before_submit(self):
        if (self.status or "pending") != "pending":
            frappe.throw("Only pending profile change requests can be submitted.")

    def before_cancel(self):
        if (self.status or "") == "approved":
            frappe.throw("Approved profile changes cannot be cancelled.")

    def on_update_after_submit(self):
        if not self.has_value_changed("status"):
            return
        if self.status == "approved":
            self._apply()
        if self.status in ("approved", "rejected"):
            self.db_set("reviewed_by", frappe.session.user)
            self.db_set("reviewed_at", frappe.utils.now_datetime())
            write_audit(
                action=f"profile_change.{self.status}",
                entity_type="VB Vendor Profile Change Request",
                entity_id=self.name,
            )

    def on_update(self):
        if cint(self.docstatus) != 0:
            return
        if not self.has_value_changed("status"):
            return
        if self.status == "approved":
            self._apply()
        if self.status in ("approved", "rejected"):
            self.db_set("reviewed_by", frappe.session.user)
            self.db_set("reviewed_at", frappe.utils.now_datetime())
            write_audit(
                action=f"profile_change.{self.status}",
                entity_type="VB Vendor Profile Change Request",
                entity_id=self.name,
            )

    def _apply(self):
        vendor = frappe.get_doc("VB Vendor", self.vendor)
        vendor.flags.from_profile_change = True
        payload = self.new_value or {}
        if isinstance(payload, str):
            payload = frappe.parse_json(payload)
        field = self.field_name
        if field == "phone" and payload.get("phone"):
            vendor.phone = payload["phone"]
        elif field == "email" and payload.get("email") is not None:
            vendor.email = payload["email"]
        elif field == "bank":
            kyc_name = frappe.db.get_value("VB Vendor KYC", {"vendor": vendor.name}, "name")
            if kyc_name:
                kyc = frappe.get_doc("VB Vendor KYC", kyc_name)
                kyc.flags.in_kyc_review = True
                for key in ("bank_name", "account_number", "ifsc_code", "beneficiary_name"):
                    if key in payload:
                        kyc.set(key, payload[key])
                kyc.save(ignore_permissions=True)
        vendor.save(ignore_permissions=True)
