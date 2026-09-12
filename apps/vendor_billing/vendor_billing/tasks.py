"""Hourly / daily jobs."""

from __future__ import annotations

import frappe

from vendor_billing.utils import derive_agreement_status


def purge_expired_portal_auth() -> None:
    if not frappe.db.exists("DocType", "VB Portal OTP"):
        return
    now = frappe.utils.now_datetime()
    frappe.db.delete("VB Portal OTP", {"expires_at": ["<", now]})
    if frappe.db.exists("DocType", "VB Portal Session"):
        frappe.db.delete("VB Portal Session", {"expires_at": ["<", now]})
    frappe.db.commit()


def refresh_agreement_statuses() -> None:
    if not frappe.db.exists("DocType", "VB Agreement"):
        return
    rows = frappe.get_all(
        "VB Agreement",
        filters={"archived": 0},
        fields=["name", "end_date", "status"],
    )
    for row in rows:
        derived = derive_agreement_status(row.end_date, row.status)
        if derived != row.status:
            frappe.db.set_value("VB Agreement", row.name, "status", derived, update_modified=False)
    frappe.db.commit()
