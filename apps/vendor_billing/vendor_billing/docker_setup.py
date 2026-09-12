"""One-time / idempotent local Docker bootstrap (users, mail, demo vendor)."""

from __future__ import annotations

from pathlib import Path

import frappe
from frappe.utils.password import update_password


SHARED_ENV = Path("/shared/portal.env")
DEMO_TOKEN = "demo-vendor-token"
PORTAL_USER = "portal-gateway@example.com"


def ensure_dev_users() -> None:
    _ensure_portal_gateway()
    _ensure_email_account()
    _ensure_notification_settings()
    _ensure_demo_vendor()
    _ensure_demo_hub()
    frappe.db.commit()


def _ensure_portal_gateway() -> None:
    if not frappe.db.exists("User", PORTAL_USER):
        user = frappe.get_doc(
            {
                "doctype": "User",
                "email": PORTAL_USER,
                "first_name": "Portal",
                "last_name": "Gateway",
                "send_welcome_email": 0,
                "user_type": "System User",
            }
        )
        user.append("roles", {"role": "VB Portal Gateway"})
        user.insert(ignore_permissions=True)
        update_password(PORTAL_USER, "portal-gateway")
    else:
        user = frappe.get_doc("User", PORTAL_USER)
        roles = {r.role for r in user.roles}
        if "VB Portal Gateway" not in roles:
            user.add_roles("VB Portal Gateway")

    if SHARED_ENV.exists() and frappe.db.get_value("User", PORTAL_USER, "api_key"):
        return

    from frappe.core.doctype.user.user import generate_keys

    keys = generate_keys(PORTAL_USER)
    user = frappe.get_doc("User", PORTAL_USER)
    api_key = user.api_key
    api_secret = keys.get("api_secret") if isinstance(keys, dict) else None
    if not api_key or not api_secret:
        frappe.throw("Could not generate portal gateway API keys")
    SHARED_ENV.parent.mkdir(parents=True, exist_ok=True)
    SHARED_ENV.write_text(
        "\n".join(
            [
                "FRAPPE_URL=http://frappe:8000",
                "FRAPPE_SITE_NAME=localhost",
                f"FRAPPE_API_KEY={api_key}",
                f"FRAPPE_API_SECRET={api_secret}",
                "PORTAL_ORIGIN=http://localhost:3000",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _ensure_email_account() -> None:
    if frappe.db.exists("Email Account", "Mailpit"):
        return
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Email Account",
                "email_account_name": "Mailpit",
                "email_id": "noreply@example.com",
                "auth_method": "Basic",
                "awaiting_password": 0,
                "smtp_server": "mailpit",
                "smtp_port": 1025,
                "use_tls": 0,
                "use_ssl_for_outgoing": 0,
                "login_id": "noreply@example.com",
                "enable_outgoing": 1,
                "default_outgoing": 1,
                "always_use_account_email_id_as_sender": 1,
                "no_smtp_authentication": 1,
            }
        )
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="Mailpit Email Account setup skipped")


def _ensure_notification_settings() -> None:
    if not frappe.db.exists("DocType", "VB Notification Settings"):
        return
    s = frappe.get_single("VB Notification Settings")
    s.portal_origin = "http://localhost:3000"
    s.save(ignore_permissions=True)


def _ensure_demo_vendor() -> None:
    if frappe.db.exists("VB Vendor", {"token": DEMO_TOKEN}):
        return
    frappe.get_doc(
        {
            "doctype": "VB Vendor",
            "vendor_name": "Demo Vendor",
            "email": "vendor@example.com",
            "phone": "9999999999",
            "token": DEMO_TOKEN,
            "status": "active",
            "kyc_status": "pending_submission",
        }
    ).insert(ignore_permissions=True)


def _ensure_demo_hub() -> None:
    if frappe.db.exists("DocType", "VB Hub") and not frappe.db.exists("VB Hub", "BLR-01"):
        frappe.get_doc(
            {
                "doctype": "VB Hub",
                "hub_name": "Bengaluru Hub",
                "code": "BLR-01",
                "state": "Karnataka",
                "state_code": "29",
                "city": "Bengaluru",
                "address": "Demo hub address",
            }
        ).insert(ignore_permissions=True)
    vendor_name = frappe.db.get_value("VB Vendor", {"token": DEMO_TOKEN}, "name")
    if not vendor_name:
        return
    vendor = frappe.get_doc("VB Vendor", vendor_name)
    dirty = False
    if frappe.db.exists("VB Hub", "BLR-01") and not any(r.hub == "BLR-01" for r in (vendor.hubs or [])):
        vendor.append("hubs", {"hub": "BLR-01"})
        dirty = True
    if frappe.db.exists("VB Billing Category", "Rent") and not any(
        r.billing_category == "Rent" for r in (vendor.categories or [])
    ):
        vendor.append("categories", {"billing_category": "Rent"})
        dirty = True
    if not any((r.state or "").lower() == "karnataka" for r in (vendor.states or [])):
        vendor.append("states", {"state": "Karnataka"})
        dirty = True
    if dirty:
        vendor.save(ignore_permissions=True)
