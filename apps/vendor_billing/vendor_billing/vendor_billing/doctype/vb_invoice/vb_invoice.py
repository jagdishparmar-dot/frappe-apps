from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate

from vendor_billing.document_flow import invoice_is_frozen, vendor_can_bill
from vendor_billing.identity import assert_invoice_not_duplicate
from vendor_billing.notifications import notify_invoice_status_change, notify_invoice_uploaded
from vendor_billing.utils import (
    billing_month_from_date,
    normalize_invoice_number,
    normalize_po_grn,
    write_audit,
)


class VBInvoice(Document):
    def before_insert(self):
        if not self.uploaded_at:
            self.uploaded_at = frappe.utils.now_datetime()
        if not self.status:
            self.status = "Pending"
        if not self.payment_status:
            self.payment_status = "none"

    def validate(self):
        self.invoice_number_normalized = normalize_invoice_number(self.invoice_number)
        self.billing_month = billing_month_from_date(self.invoice_date)
        self.po_number = normalize_po_grn(self.po_number)
        self.grn_number = normalize_po_grn(self.grn_number)
        if flt(self.amount) <= 0:
            frappe.throw("Amount must be a number greater than 0.")
        if self.due_date and self.invoice_date and getdate(self.due_date) < getdate(self.invoice_date):
            frappe.throw("Due date cannot be before invoice date.")
        if self.document_type in ("credit_note", "debit_note") and not self.linked_invoice:
            frappe.throw("Credit/debit notes must link to an original invoice.")
        if self.linked_invoice:
            self._validate_linked_invoice()
        self._validate_payment()
        if self.archived and not self.deletion_remarks:
            frappe.throw("Deletion remarks are required to archive an invoice.")
        if self.archived and not self.archived_at:
            self.archived_at = frappe.utils.now_datetime()
        if not self.archived:
            self.archived_at = None
        if invoice_is_frozen(self) and self.has_value_changed("status") and self.status != "Paid":
            frappe.throw("Paid invoices cannot be moved back to another status.")
        assert_invoice_not_duplicate(self)

    def before_submit(self):
        if not self.invoice_file:
            frappe.throw("Invoice file is required before submit.")
        vendor_can_bill(self.vendor)
        if (self.status or "Pending") not in ("Pending", "Hold"):
            self.status = "Pending"
        if invoice_is_frozen(self):
            frappe.throw("A paid invoice cannot be submitted from draft. Create a new document.")

    def on_submit(self):
        write_audit(action="invoice.submit", entity_type="VB Invoice", entity_id=self.name)
        notify_invoice_uploaded(self)

    def before_cancel(self):
        if invoice_is_frozen(self):
            frappe.throw("Paid invoices cannot be cancelled.")
        if (self.payment_status or "none") in ("approved", "scheduled"):
            frappe.throw("Cancel payment approval or the payment schedule before cancelling this invoice.")
        if frappe.db.exists("VB Invoice", {"linked_invoice": self.name, "docstatus": 1}):
            frappe.throw("Cancel linked credit or debit notes before returning or cancelling this invoice.")

    def on_cancel(self):
        write_audit(action="invoice.cancel", entity_type="VB Invoice", entity_id=self.name)

    def on_update(self):
        if cint(self.docstatus) != 0:
            return
        if self.has_value_changed("status") or self.has_value_changed("payment_status"):
            write_audit(
                action="invoice.status_change",
                entity_type="VB Invoice",
                entity_id=self.name,
                metadata={"status": self.status, "payment_status": self.payment_status},
            )

    def on_update_after_submit(self):
        if self.has_value_changed("status") or self.has_value_changed("payment_status"):
            write_audit(
                action="invoice.status_change",
                entity_type="VB Invoice",
                entity_id=self.name,
                metadata={"status": self.status, "payment_status": self.payment_status},
            )
            notify_invoice_status_change(self)

    def after_insert(self):
        write_audit(action="invoice.create", entity_type="VB Invoice", entity_id=self.name)

    def _validate_linked_invoice(self):
        linked = frappe.db.get_value(
            "VB Invoice",
            self.linked_invoice,
            ["vendor", "docstatus", "status"],
            as_dict=True,
        )
        if not linked:
            frappe.throw("Linked invoice was not found.")
        if linked.vendor != self.vendor:
            frappe.throw("Credit/debit notes must link to an invoice from the same vendor.")
        if cint(linked.docstatus) != 1:
            frappe.throw("Credit/debit notes must link to a submitted invoice.")

    def _validate_payment(self):
        if self.payment_status == "scheduled" and not self.scheduled_pay_date:
            frappe.throw("Scheduled pay date is required when payment status is scheduled.")
        if self.payment_status == "paid":
            if not self.paid_date:
                frappe.throw("Paid date is required when payment status is paid.")
            if self.status == "Pending":
                self.status = "Paid"
        if self.status == "Paid" and self.payment_status == "none":
            self.payment_status = "paid"

    def get_challan_number(self) -> str:
        from vendor_billing.print_utils import challan_number

        return challan_number(self)

    def get_amount_in_words(self) -> str:
        from vendor_billing.print_utils import amount_in_words_inr

        return amount_in_words_inr(self.amount)
