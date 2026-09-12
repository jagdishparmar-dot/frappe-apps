"""Vendor portal session guard.

Vendors are not Frappe Users. After OTP verify, a VB Portal Session row is
keyed by the vendor share token (TTL 2 hours).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _


class PortalAuthError(frappe.AuthenticationError):
    pass


def require_portal_session(token: str | None) -> dict[str, Any]:
    token = (token or "").strip()
    if not token:
        frappe.throw(_("OTP Verification Required"), PortalAuthError)

    session = frappe.db.get_value(
        "VB Portal Session",
        token,
        ["name", "token", "phone", "expires_at", "vendor"],
        as_dict=True,
    )
    if not session:
        frappe.throw(_("OTP Verification Required"), PortalAuthError)

    if session.expires_at and session.expires_at < frappe.utils.now_datetime():
        frappe.delete_doc("VB Portal Session", session.name, ignore_permissions=True, force=True)
        frappe.throw(_("OTP Verification Required"), PortalAuthError)

    vendor = frappe.db.get_value(
        "VB Vendor",
        session.vendor,
        ["name", "token", "vendor_name", "phone", "email", "kyc_status", "archived"],
        as_dict=True,
    )
    if not vendor or vendor.archived or vendor.token != token:
        frappe.delete_doc("VB Portal Session", session.name, ignore_permissions=True, force=True)
        frappe.throw(_("OTP Verification Required"), PortalAuthError)

    return {"session": session, "vendor": vendor}


def assert_vendor_owns(doc_vendor: str, session_vendor: str) -> None:
    if doc_vendor != session_vendor:
        frappe.throw(_("Forbidden"), frappe.PermissionError)
