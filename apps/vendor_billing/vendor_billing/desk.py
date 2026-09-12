"""Desk helpers: portal link, archive/restore, KYC, invoice payment, queue review."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, nowdate, now_datetime

from vendor_billing.document_flow import invoice_is_frozen, return_submitted_invoice
from vendor_billing.notifications import portal_url

RESTORE_ROLES = {"System Manager", "VB Admin", "VB Vendor Manager", "VB AP Operator"}
INVOICE_STATUSES = {"Pending", "Paid", "Hold", "Rejected"}
PAYMENT_STATUSES = {"none", "approved", "scheduled", "paid"}


def _can_restore() -> bool:
    return bool(set(frappe.get_roles()) & RESTORE_ROLES)


@frappe.whitelist()
def portal_share_url(vendor: str) -> str:
    frappe.has_permission("VB Vendor", "read", throw=True)
    token = frappe.db.get_value("VB Vendor", vendor, "token")
    if not token:
        frappe.throw(_("Vendor has no portal token."))
    return portal_url(token)


@frappe.whitelist()
def archive_doc(doctype: str, name: str, remarks: str) -> None:
    if doctype not in ("VB Vendor", "VB Invoice", "VB Agreement"):
        frappe.throw(_("Cannot archive this document type."))
    if not remarks:
        frappe.throw(_("Deletion remarks are required."))
    frappe.has_permission(doctype, "write", throw=True)
    doc = frappe.get_doc(doctype, name)
    if doctype in ("VB Invoice", "VB Agreement") and cint(doc.docstatus) == 2:
        frappe.throw(_("Cancelled documents cannot be archived."))
    doc.archived = 1
    doc.deletion_remarks = remarks
    doc.archived_at = now_datetime()
    doc.save()


@frappe.whitelist()
def restore_doc(doctype: str, name: str) -> None:
    if doctype not in ("VB Vendor", "VB Invoice", "VB Agreement"):
        frappe.throw(_("Cannot restore this document type."))
    if not _can_restore():
        frappe.throw(_("You cannot restore archived documents."), frappe.PermissionError)
    frappe.has_permission(doctype, "write", throw=True)
    doc = frappe.get_doc(doctype, name)
    doc.archived = 0
    doc.deletion_remarks = None
    doc.archived_at = None
    doc.save()


@frappe.whitelist()
def verify_kyc(kyc: str, remarks: str | None = None) -> None:
    frappe.has_permission("VB Vendor KYC", "write", throw=True)
    frappe.get_doc("VB Vendor KYC", kyc).verify(remarks)


@frappe.whitelist()
def reject_kyc(kyc: str, remarks: str) -> None:
    frappe.has_permission("VB Vendor KYC", "write", throw=True)
    frappe.get_doc("VB Vendor KYC", kyc).reject(remarks)


@frappe.whitelist()
def apply_invoice_status(
    invoice: str,
    status: str,
    payment_status: str | None = None,
    scheduled_pay_date: str | None = None,
    paid_date: str | None = None,
    payment_reference: str | None = None,
    payment_remarks: str | None = None,
    remarks: str | None = None,
) -> dict:
    """Desk payment/status dialog. Mirrors the old Next admin `updateInvoiceStatus` rules."""
    frappe.has_permission("VB Invoice", "write", throw=True)
    if status not in INVOICE_STATUSES:
        frappe.throw(_("Invalid status value. Must be Pending, Paid, Hold, or Rejected."))

    doc = frappe.get_doc("VB Invoice", invoice)
    if doc.archived:
        frappe.throw(_("Archived invoices cannot be updated."))
    if cint(doc.docstatus) == 0:
        frappe.throw(_("Submit the invoice before reviewing status or payment."))
    if cint(doc.docstatus) == 2:
        frappe.throw(_("Cancelled invoices cannot be reviewed."))
    if invoice_is_frozen(doc) and not (status == "Paid" and (payment_status or "paid") == "paid"):
        frappe.throw(_("Paid invoices are frozen and cannot change status."))

    next_pay = doc.payment_status or "none"
    next_scheduled = scheduled_pay_date if scheduled_pay_date is not None else doc.scheduled_pay_date
    next_paid = paid_date if paid_date is not None else doc.paid_date
    next_ref = payment_reference if payment_reference is not None else doc.payment_reference
    next_pay_remarks = payment_remarks if payment_remarks is not None else doc.payment_remarks

    if status == "Paid":
        next_pay = "paid"
        if not next_paid:
            next_paid = nowdate()
    elif status == "Rejected":
        next_pay = "none"
        next_scheduled = None
        next_paid = None
        next_ref = None

    if payment_status:
        if payment_status not in PAYMENT_STATUSES:
            frappe.throw(_("Invalid payment status."))
        next_pay = payment_status
        if next_pay == "paid":
            status = "Paid"
            if not next_paid:
                next_paid = nowdate()

    if next_pay == "scheduled" and not next_scheduled:
        frappe.throw(_("Scheduled pay date is required when payment status is scheduled."))
    if next_pay == "paid" and not next_paid:
        frappe.throw(_("Paid date is required when payment status is paid."))

    doc.status = status
    doc.payment_status = next_pay
    doc.scheduled_pay_date = next_scheduled or None
    doc.paid_date = next_paid or None
    doc.payment_reference = next_ref
    doc.payment_remarks = next_pay_remarks
    if remarks is not None:
        doc.remarks = remarks
    doc.save()
    if status == "Rejected":
        doc.flags.ignore_permissions = True
        doc.cancel()
    return {
        "status": doc.status,
        "payment_status": doc.payment_status,
    }


@frappe.whitelist()
def return_invoice_to_vendor(invoice: str, remarks: str | None = None) -> dict:
    """AP send-back: cancel the submitted invoice and open a draft for the vendor."""
    frappe.has_permission("VB Invoice", "write", throw=True)
    name = return_submitted_invoice(invoice, remarks=remarks)
    return {"amended_invoice": name}


def _ensure_submitted(doc) -> None:
    if cint(doc.docstatus) == 2:
        frappe.throw(_("This document is cancelled."))
    if cint(doc.docstatus) == 0:
        doc.flags.ignore_permissions = True
        doc.submit()
        doc.reload()


@frappe.whitelist()
def review_registration(name: str, action: str, remarks: str | None = None) -> None:
    frappe.has_permission("VB Vendor Registration Request", "write", throw=True)
    if action not in ("approve", "reject"):
        frappe.throw(_("Unknown action."))
    doc = frappe.get_doc("VB Vendor Registration Request", name)
    if doc.status != "pending":
        frappe.throw(_("This request has already been reviewed."))
    if action == "reject" and not remarks:
        frappe.throw(_("Rejection remarks are required."))
    _ensure_submitted(doc)
    doc.status = "approved" if action == "approve" else "rejected"
    if remarks:
        doc.review_remarks = remarks
    doc.save()
    if action == "reject":
        doc.cancel()


@frappe.whitelist()
def review_profile_change(name: str, action: str, remarks: str | None = None) -> None:
    frappe.has_permission("VB Vendor Profile Change Request", "write", throw=True)
    if action not in ("approve", "reject"):
        frappe.throw(_("Unknown action."))
    doc = frappe.get_doc("VB Vendor Profile Change Request", name)
    if doc.status != "pending":
        frappe.throw(_("This request has already been reviewed."))
    if action == "reject" and not remarks:
        frappe.throw(_("Rejection remarks are required."))
    _ensure_submitted(doc)
    doc.status = "approved" if action == "approve" else "rejected"
    if remarks:
        doc.review_remarks = remarks
    doc.save()
    if action == "reject":
        doc.cancel()
