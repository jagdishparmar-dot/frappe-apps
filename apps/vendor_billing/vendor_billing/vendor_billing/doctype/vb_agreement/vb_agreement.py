from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from vendor_billing.utils import derive_agreement_status, write_audit


class VBAgreement(Document):
    def before_insert(self):
        if not self.uploaded_by:
            self.uploaded_by = frappe.session.user

    def validate(self):
        if self.start_date and self.end_date and getdate(self.end_date) < getdate(self.start_date):
            frappe.throw("End date cannot be before start date.")
        self.status = derive_agreement_status(self.end_date, self.status)
        if self.archived and not self.deletion_remarks:
            frappe.throw("Deletion remarks are required to archive an agreement.")
        if self.archived and not self.archived_at:
            self.archived_at = frappe.utils.now_datetime()
        if not self.archived:
            self.archived_at = None

    def before_submit(self):
        if not self.agreement_file:
            frappe.throw("Attach the signed agreement before issuing it to the vendor.")
        if not self.start_date or not self.end_date:
            frappe.throw("Start and end dates are required before submit.")

    def on_submit(self):
        write_audit(action="agreement.issue", entity_type="VB Agreement", entity_id=self.name)

    def on_cancel(self):
        write_audit(action="agreement.cancel", entity_type="VB Agreement", entity_id=self.name)

    def after_insert(self):
        write_audit(action="agreement.create", entity_type="VB Agreement", entity_id=self.name)
