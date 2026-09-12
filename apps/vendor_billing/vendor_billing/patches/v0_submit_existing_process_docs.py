from __future__ import annotations

import frappe


def execute() -> None:
    """Lock existing process documents that are already in a live state."""
    if frappe.db.exists("DocType", "VB Invoice"):
        frappe.db.sql(
            "update `tabVB Invoice` set docstatus=1 where docstatus=0 and ifnull(status,'') != 'Rejected'"
        )
        frappe.db.sql(
            "update `tabVB Invoice` set docstatus=2 where docstatus=0 and status='Rejected'"
        )
    if frappe.db.exists("DocType", "VB Agreement"):
        frappe.db.sql("update `tabVB Agreement` set docstatus=1 where docstatus=0")
    if frappe.db.exists("DocType", "VB Vendor Registration Request"):
        frappe.db.sql(
            "update `tabVB Vendor Registration Request` set docstatus=1 where docstatus=0 and status in ('pending','approved')"
        )
        frappe.db.sql(
            "update `tabVB Vendor Registration Request` set docstatus=2 where docstatus=0 and status='rejected'"
        )
    if frappe.db.exists("DocType", "VB Vendor Profile Change Request"):
        frappe.db.sql(
            "update `tabVB Vendor Profile Change Request` set docstatus=1 where docstatus=0 and status in ('pending','approved')"
        )
        frappe.db.sql(
            "update `tabVB Vendor Profile Change Request` set docstatus=2 where docstatus=0 and status='rejected'"
        )
    if frappe.db.exists("DocType", "VB Vendor KYC"):
        frappe.db.sql(
            "update `tabVB Vendor KYC` set docstatus=1 where docstatus=0 and kyc_status='verified'"
        )
