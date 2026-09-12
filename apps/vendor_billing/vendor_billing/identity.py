from __future__ import annotations

import frappe
from frappe import _

from vendor_billing.utils import normalize_invoice_number, billing_month_from_date


def find_duplicate_invoice(
    vendor: str,
    invoice_number: str,
    invoice_date,
    document_type: str,
    exclude: str | None = None,
):
    normalized = normalize_invoice_number(invoice_number)
    month = billing_month_from_date(invoice_date)
    if not normalized or not month:
        return None
    filters = {
        "vendor": vendor,
        "invoice_number_normalized": normalized,
        "billing_month": month,
        "document_type": document_type or "invoice",
        "archived": 0,
        "docstatus": ["<", 2],
    }
    names = frappe.get_all("VB Invoice", filters=filters, pluck="name", ignore_permissions=True)
    for name in names:
        if exclude and name == exclude:
            continue
        return name
    return None


def assert_invoice_not_duplicate(doc) -> None:
    dup = find_duplicate_invoice(
        doc.vendor,
        doc.invoice_number,
        doc.invoice_date,
        doc.document_type,
        exclude=doc.name if not doc.is_new() else None,
    )
    if not dup:
        return
    month = billing_month_from_date(doc.invoice_date) or ""
    labels = {"invoice": "Invoice", "credit_note": "Credit Note", "debit_note": "Debit Note"}
    type_label = labels.get(doc.document_type or "invoice", "Invoice")
    from vendor_billing.utils import format_billing_month_label

    frappe.throw(
        _("{0} {1} was already submitted for {2}.").format(
            type_label, doc.invoice_number, format_billing_month_label(month)
        )
    )


def find_vendor_duplicate(phone_normalized: str, email: str | None, gst: str | None, exclude: str | None = None):
    if phone_normalized:
        names = frappe.get_all(
            "VB Vendor",
            filters={"phone_normalized": phone_normalized, "archived": 0},
            pluck="name",
            ignore_permissions=True,
        )
        for name in names:
            if exclude and name == exclude:
                continue
            return name
    if email:
        names = frappe.get_all(
            "VB Vendor",
            filters={"email": email, "archived": 0},
            pluck="name",
            ignore_permissions=True,
        )
        for name in names:
            if exclude and name == exclude:
                continue
            if name:
                return name
    return None
