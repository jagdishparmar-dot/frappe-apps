"""Guest-callable portal API. Next.js is the only client.

    POST {FRAPPE_URL}/api/method/vendor_billing.portal.otp_send
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from vendor_billing import __version__ as APP_VERSION
from vendor_billing.document_flow import submit_as_system
from vendor_billing.notifications import send_mail
from vendor_billing.portal_auth import require_portal_session
from vendor_billing.portal_workspace import (
    agreement_file as workspace_agreement_file,
    agreements as workspace_agreements,
    company_profile as workspace_company,
    full_payload,
    invoice_file as workspace_invoice_file,
    invoice_get as workspace_invoice_get,
    invoice_update as workspace_invoice_update,
    invoice_upload as workspace_invoice_upload,
    kyc_file as workspace_kyc_file,
    kyc_submit as workspace_kyc_submit,
    notification_read as workspace_notification_read,
    notifications as workspace_notifications,
    profile_change as workspace_profile_change,
)
from vendor_billing.sms import get_smartping_config, send_otp_sms
from vendor_billing.utils import (
    generate_otp,
    hash_otp,
    mask_email,
    mask_phone,
    normalize_phone,
    otp_matches,
)

OTP_MINUTES = 5
SESSION_HOURS = 2


def _otp_console_enabled() -> bool:
    """Local Docker / developer_mode: print OTP to stdout until SMS/email is wired."""
    try:
        if int(frappe.conf.get("developer_mode") or 0):
            return True
    except (TypeError, ValueError):
        pass
    return bool(frappe.conf.get("vb_otp_console"))


def _print_otp_for_testing(token: str, phone: str, otp: str) -> None:
    banner = "\n".join(
        [
            "",
            "======== VB PORTAL OTP (local testing) ========",
            f"  vendor token : {token}",
            f"  phone        : {phone}",
            f"  otp          : {otp}",
            "  SMS/email not required in developer_mode.",
            "===============================================",
            "",
        ]
    )
    print(banner, flush=True)
    try:
        frappe.logger("vendor_billing").info(banner)
    except Exception:
        pass


def _rate_limit(key: str, limit: int, window_sec: int, message: str) -> None:
    cache = frappe.cache()
    cache_key = f"vb-rl:{key}"
    count = int(cache.get_value(cache_key) or 0) + 1
    cache.set_value(cache_key, count, expires_in_sec=window_sec)
    if count > limit:
        frappe.throw(message)


def _vendor_by_token(token: str):
    token = (token or "").strip()
    if not token:
        frappe.throw(_("Invalid vendor portal link. Please check with administrator."))
    vendor = frappe.db.get_value(
        "VB Vendor",
        {"token": token, "archived": 0},
        ["name", "vendor_name", "email", "phone", "token", "kyc_status"],
        as_dict=True,
    )
    if not vendor:
        frappe.throw(_("Invalid vendor portal link. Please check with administrator."))
    return vendor


def _payload(vendor) -> dict:
    return full_payload(vendor)


@frappe.whitelist(allow_guest=True)
def check(token: str | None = None) -> dict:
    vendor = _vendor_by_token(token)
    email = (vendor.email or "").strip()
    return {
        "success": True,
        "name": vendor.vendor_name,
        "maskedPhone": mask_phone(vendor.phone),
        "maskedEmail": mask_email(email) if email else None,
    }


@frappe.whitelist(allow_guest=True)
def otp_send(token: str | None = None, phone: str | None = None) -> dict:
    if not token or not phone:
        frappe.throw(_("Token and phone number are required."))
    ip = frappe.local.request_ip if hasattr(frappe.local, "request_ip") else "0"
    _rate_limit(f"otp-send:{token}:{ip}", 5, 15 * 60, "Too many OTP requests. Please wait before trying again.")

    vendor = _vendor_by_token(token)
    if normalize_phone(phone) != normalize_phone(vendor.phone):
        frappe.throw(_("This mobile number is not registered for this vendor link. Please contact administrator."))

    otp = generate_otp(6)
    expires = add_to_date(now_datetime(), minutes=OTP_MINUTES)
    email = (vendor.email or "").strip()
    sms_cfg = get_smartping_config()
    can_email = bool(email)
    console_ok = _otp_console_enabled()

    if not sms_cfg["enabled"] and not can_email and not console_ok:
        frappe.throw(_("Verification delivery is not configured. Please contact administrator."))

    if frappe.db.exists("VB Portal OTP", token):
        doc = frappe.get_doc("VB Portal OTP", token)
        doc.otp_hash = hash_otp(otp)
        doc.phone = normalize_phone(phone)
        doc.expires_at = expires
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": "VB Portal OTP",
                "token": token,
                "otp_hash": hash_otp(otp),
                "phone": normalize_phone(phone),
                "expires_at": expires,
            }
        ).insert(ignore_permissions=True)

    if console_ok:
        _print_otp_for_testing(token, normalize_phone(phone), otp)

    sms_sent = False
    email_sent = False
    if sms_cfg["enabled"]:
        result = send_otp_sms(normalize_phone(phone), otp)
        sms_sent = bool(result.get("ok"))
    if can_email:
        try:
            send_mail(
                email,
                "Vendor portal verification code",
                f"<p>Your verification code is <b>{otp}</b>. It is valid for {OTP_MINUTES} minutes.</p>",
            )
            email_sent = True
        except Exception:
            email_sent = False

    if not sms_sent and not email_sent and not console_ok:
        frappe.delete_doc("VB Portal OTP", token, ignore_permissions=True, force=True)
        frappe.throw(_("Could not send verification code. Please try again later."))

    masked = mask_email(email) if email else None
    channels: list[str] = []
    if console_ok:
        channels.append("the server console (developer_mode)")
    if sms_sent:
        channels.append("your registered mobile number")
    if email_sent and masked:
        channels.append(f"your registered email ({masked})")
    elif email_sent:
        channels.append("your registered email")
    if len(channels) == 1:
        message = f"Verification code sent to {channels[0]}."
    else:
        message = "Verification code sent to " + ", ".join(channels[:-1]) + f", and {channels[-1]}."

    payload = {
        "success": True,
        "message": message,
        "smsSent": sms_sent,
        "emailSent": email_sent,
        "consoleLogged": console_ok,
        "maskedEmail": masked,
    }
    if console_ok:
        payload["devOtp"] = otp
    return payload


@frappe.whitelist(allow_guest=True)
def otp_verify(token: str | None = None, phone: str | None = None, otp: str | None = None) -> dict:
    if not token or not phone or not otp:
        frappe.throw(_("Token, phone number, and OTP are required."))
    _rate_limit(f"otp-fail:{token}", 8, 15 * 60, "Too many failed OTP attempts. Please request a new OTP later.")

    vendor = _vendor_by_token(token)
    stored = frappe.db.get_value(
        "VB Portal OTP",
        token,
        ["name", "otp_hash", "phone", "expires_at"],
        as_dict=True,
    )
    if not stored:
        frappe.throw(_("No active OTP request found. Please request a new OTP."))
    if stored.expires_at and stored.expires_at < now_datetime():
        frappe.delete_doc("VB Portal OTP", stored.name, ignore_permissions=True, force=True)
        frappe.throw(_("OTP has expired. Please request a new OTP."))
    if not otp_matches(stored.otp_hash, otp) or normalize_phone(phone) != stored.phone:
        frappe.throw(_("Invalid OTP code. Please try again."))

    frappe.delete_doc("VB Portal OTP", stored.name, ignore_permissions=True, force=True)
    expires = add_to_date(now_datetime(), hours=SESSION_HOURS)
    if frappe.db.exists("VB Portal Session", token):
        session = frappe.get_doc("VB Portal Session", token)
        session.phone = stored.phone
        session.vendor = vendor.name
        session.expires_at = expires
        session.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": "VB Portal Session",
                "token": token,
                "vendor": vendor.name,
                "phone": stored.phone,
                "expires_at": expires,
            }
        ).insert(ignore_permissions=True)

    return {"success": True, "message": "OTP verified successfully.", **_payload(vendor)}


@frappe.whitelist(allow_guest=True)
def otp_logout(token: str | None = None) -> dict:
    token = (token or "").strip()
    if not token:
        frappe.throw(_("Token is required."))
    if frappe.db.exists("VB Portal Session", token):
        frappe.delete_doc("VB Portal Session", token, ignore_permissions=True, force=True)
    if frappe.db.exists("VB Portal OTP", token):
        frappe.delete_doc("VB Portal OTP", token, ignore_permissions=True, force=True)
    return {"success": True, "message": "Logged out of vendor portal session."}


@frappe.whitelist(allow_guest=True)
def session_bootstrap(token: str | None = None) -> dict:
    ctx = require_portal_session(token)
    return _payload(ctx["vendor"])


@frappe.whitelist(allow_guest=True)
def company_profile(token: str | None = None) -> dict:
    require_portal_session(token)
    return workspace_company()


@frappe.whitelist(allow_guest=True)
def register(
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    gst_number: str | None = None,
    gstNumber: str | None = None,
    states: list | str | None = None,
    categories: list | str | None = None,
    message: str | None = None,
) -> dict:
    ip = getattr(frappe.local, "request_ip", "0") or "0"
    _rate_limit(f"register:{ip}", 5, 15 * 60, "Too many registration requests. Please wait.")
    if isinstance(states, str):
        states = frappe.parse_json(states)
    if isinstance(categories, str):
        categories = frappe.parse_json(categories)
    gst = (gst_number or gstNumber or "").strip()
    doc = frappe.get_doc(
        {
            "doctype": "VB Vendor Registration Request",
            "applicant_name": name,
            "email": email,
            "phone": phone,
            "gst_number": gst or None,
            "message": message,
            "states": [{"state": s} for s in (states or [])],
            "categories": [{"billing_category": c} for c in (categories or [])],
        }
    )
    doc.insert(ignore_permissions=True)
    submit_as_system(doc)
    return {
        "success": True,
        "id": doc.name,
        "message": "Request submitted successfully. Our accounts team will review it and send a portal link if approved.",
    }


@frappe.whitelist(allow_guest=True)
def kyc_submit(**kwargs) -> dict:
    return workspace_kyc_submit(**kwargs)


@frappe.whitelist(allow_guest=True)
def kyc_file(**kwargs) -> dict:
    return workspace_kyc_file(**kwargs)


@frappe.whitelist(allow_guest=True)
def invoice_upload(**kwargs) -> dict:
    return workspace_invoice_upload(**kwargs)


@frappe.whitelist(allow_guest=True)
def invoice_get(**kwargs) -> dict:
    return workspace_invoice_get(**kwargs)


@frappe.whitelist(allow_guest=True)
def invoice_update(**kwargs) -> dict:
    return workspace_invoice_update(**kwargs)


@frappe.whitelist(allow_guest=True)
def invoice_file(**kwargs) -> dict:
    return workspace_invoice_file(**kwargs)


@frappe.whitelist(allow_guest=True)
def agreements(**kwargs) -> dict:
    return workspace_agreements(**kwargs)


@frappe.whitelist(allow_guest=True)
def agreement_file(**kwargs) -> dict:
    return workspace_agreement_file(**kwargs)


@frappe.whitelist(allow_guest=True)
def profile_change(**kwargs) -> dict:
    return workspace_profile_change(**kwargs)


@frappe.whitelist(allow_guest=True)
def notifications(**kwargs) -> dict:
    return workspace_notifications(**kwargs)


@frappe.whitelist(allow_guest=True)
def notification_read(**kwargs) -> dict:
    return workspace_notification_read(**kwargs)


@frappe.whitelist(allow_guest=True)
def ping() -> dict:
    return {"ok": True, "app": "vendor_billing", "version": APP_VERSION}
