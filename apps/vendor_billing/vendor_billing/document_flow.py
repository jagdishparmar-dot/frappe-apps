"""Submit / cancel / amend helpers for vendor-management process documents.

Transactional docs (invoice, KYC freeze, issued agreement, registration,
profile change) use Frappe docstatus so submitted records cannot be edited
except through the review actions on allow_on_submit fields.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


def vendor_can_bill(vendor) -> None:
    if isinstance(vendor, str):
        vendor = frappe.get_doc("VB Vendor", vendor)
    if vendor.archived:
        frappe.throw(_("Archived vendors cannot submit billing documents."))
    if (vendor.status or "active") != "active":
        frappe.throw(_("Inactive vendors cannot submit billing documents."))
    if (vendor.kyc_status or "") != "verified":
        frappe.throw(_("KYC must be verified before submitting invoices."))


def invoice_is_frozen(doc) -> bool:
    return (doc.status or "") == "Paid" or (doc.payment_status or "") == "paid"


def assert_invoice_editable_by_vendor(doc) -> None:
    if cint(doc.docstatus) != 0:
        frappe.throw(
            _("This invoice is locked for AP review. Accounts must return it before you can edit.")
        )
    if invoice_is_frozen(doc):
        frappe.throw(_("Paid invoices cannot be edited."))


def submit_as_system(doc) -> None:
    if cint(doc.docstatus) != 0:
        return
    doc.flags.ignore_permissions = True
    doc.submit()


def return_submitted_invoice(doc, remarks: str | None = None) -> str:
    """Cancel a submitted invoice and open a draft amendment for the vendor."""
    if isinstance(doc, str):
        doc = frappe.get_doc("VB Invoice", doc)
    if cint(doc.docstatus) != 1:
        frappe.throw(_("Only submitted invoices can be returned to the vendor."))
    if invoice_is_frozen(doc):
        frappe.throw(_("Paid invoices cannot be returned."))
    if remarks:
        doc.remarks = remarks
        doc.save(ignore_permissions=True)
    name = doc.name
    doc.flags.ignore_permissions = True
    doc.cancel()
    cancelled = frappe.get_doc("VB Invoice", name)
    amended = frappe.copy_doc(cancelled)
    amended.docstatus = 0
    amended.status = "Pending"
    amended.payment_status = "none"
    amended.scheduled_pay_date = None
    amended.paid_date = None
    amended.payment_reference = None
    amended.amended_from = name
    amended.insert(ignore_permissions=True)
    return amended.name
