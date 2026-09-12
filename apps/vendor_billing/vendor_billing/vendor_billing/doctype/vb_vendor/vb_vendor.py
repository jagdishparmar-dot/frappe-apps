from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint

from vendor_billing.identity import find_vendor_duplicate
from vendor_billing.utils import new_portal_token, normalize_phone, write_audit


class VBVendor(Document):
    def before_insert(self):
        if not self.token:
            self.token = new_portal_token()
        self._normalize()

    def validate(self):
        self._normalize()
        dup = find_vendor_duplicate(
            self.phone_normalized,
            self.email,
            self.gst_number,
            exclude=None if self.is_new() else self.name,
        )
        if dup:
            frappe.throw(f"A vendor with this phone or email already exists ({dup}).")
        if self.archived and not self.deletion_remarks:
            frappe.throw("Deletion remarks are required to archive a vendor.")
        if self.archived and not self.archived_at:
            self.archived_at = frappe.utils.now_datetime()
        if not self.archived:
            self.archived_at = None
        self._lock_verified_contact()

    def _lock_verified_contact(self):
        if self.is_new() or self.flags.from_profile_change:
            return
        roles = set(frappe.get_roles())
        if "System Manager" in roles:
            return
        prev = self.get_doc_before_save()
        was_verified = bool(prev and (prev.kyc_status or "") == "verified")
        is_verified = (self.kyc_status or "") == "verified"
        if not (was_verified or is_verified):
            return
        if self.has_value_changed("phone") or self.has_value_changed("email"):
            frappe.throw(
                "Phone and email can only be changed through an approved profile change request after KYC is verified."
            )
        if self.has_value_changed("kyc_status"):
            frappe.throw("KYC status is controlled by the KYC verification process.")

    def on_update(self):
        write_audit(
            action="vendor.update",
            entity_type="VB Vendor",
            entity_id=self.name,
            metadata={"kyc_status": self.kyc_status, "archived": self.archived},
        )
        self._sync_kyc_status()

    def after_insert(self):
        write_audit(action="vendor.create", entity_type="VB Vendor", entity_id=self.name)
        if not frappe.db.exists("VB Vendor KYC", {"vendor": self.name}):
            frappe.get_doc({"doctype": "VB Vendor KYC", "vendor": self.name, "kyc_status": self.kyc_status}).insert(
                ignore_permissions=True
            )

    def _normalize(self):
        self.phone_normalized = normalize_phone(self.phone)
        if not self.phone_normalized:
            frappe.throw("A valid phone number is required.")

    def _sync_kyc_status(self):
        if not self.has_value_changed("kyc_status"):
            return
        name = frappe.db.get_value("VB Vendor KYC", {"vendor": self.name}, ["name", "docstatus"], as_dict=True)
        if name and cint(name.docstatus) != 1:
            frappe.db.set_value("VB Vendor KYC", name.name, "kyc_status", self.kyc_status, update_modified=False)

    def archive(self, remarks: str):
        self.archived = 1
        self.deletion_remarks = remarks
        self.archived_at = frappe.utils.now_datetime()
        self.save(ignore_permissions=True)

    def restore(self):
        self.archived = 0
        self.deletion_remarks = None
        self.archived_at = None
        self.save(ignore_permissions=True)
