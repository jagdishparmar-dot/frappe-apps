from __future__ import annotations

import hashlib
import hmac
import re
import secrets

import frappe
from frappe.utils import getdate

PO_GRN_RE = re.compile(r"^[A-Za-z0-9/_\- ]*$")


def site_pepper() -> str:
    return frappe.conf.get("encryption_key") or frappe.local.conf.get("encryption_key") or "vendor-billing"


def new_portal_token() -> str:
    return secrets.token_urlsafe(18)


def generate_otp(length: int = 6) -> str:
    n = secrets.randbelow(10**length)
    return str(n).zfill(length)


def hash_otp(otp: str) -> str:
    return hmac.new(site_pepper().encode(), otp.encode(), hashlib.sha256).hexdigest()


def otp_matches(stored_hash: str, otp: str) -> bool:
    digest = hash_otp(otp)
    return hmac.compare_digest(stored_hash, digest)


def normalize_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


def normalize_invoice_number(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).upper()


def billing_month_from_date(value) -> str | None:
    d = getdate(value) if value else None
    if not d:
        return None
    return f"{d.year:04d}-{d.month:02d}"


def format_billing_month_label(billing_month: str) -> str:
    match = re.match(r"^(\d{4})-(\d{2})$", billing_month or "")
    if not match:
        return billing_month
    months = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )
    idx = int(match.group(2)) - 1
    month = months[idx] if 0 <= idx < 12 else match.group(2)
    return f"{month} {match.group(1)}"


def normalize_po_grn(value: str | None) -> str | None:
    trimmed = (value or "").strip()
    if not trimmed:
        return None
    if len(trimmed) > 64:
        frappe.throw("PO/GRN reference must be at most 64 characters.")
    if not PO_GRN_RE.match(trimmed):
        frappe.throw("PO/GRN reference may only contain letters, numbers, spaces, /, -, and _.")
    return trimmed


def mask_phone(phone: str) -> str:
    digits = normalize_phone(phone)
    if len(digits) < 4:
        return "****"
    return f"{digits[:2]}******{digits[-2:]}"


def mask_email(email: str) -> str:
    if "@" not in (email or ""):
        return ""
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


def derive_agreement_status(end_date, stored_status: str | None) -> str:
    if stored_status == "Terminated":
        return "Terminated"
    end = getdate(end_date) if end_date else None
    if not end:
        return stored_status or "Active"
    today = getdate()
    delta = (end - today).days
    if delta < 0:
        return "Expired"
    if delta <= 30:
        return "Expiring Soon"
    return "Active"


def write_audit(
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_type: str = "admin",
    metadata: dict | None = None,
) -> None:
    user = frappe.session.user if frappe.session else "Guest"
    actor_label = user
    actor_id = user
    if user == "Guest":
        actor_type = actor_type or "system"
        actor_id = None
        actor_label = "Guest"
    try:
        frappe.get_doc(
            {
                "doctype": "VB Audit Log",
                "actor_type": actor_type,
                "actor_id": actor_id,
                "actor_label": actor_label,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "metadata": metadata,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="VB Audit Log insert failed")
