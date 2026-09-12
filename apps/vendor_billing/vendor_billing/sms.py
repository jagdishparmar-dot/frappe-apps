"""SmartPing / Omni SMS — same contract as the Next.js portal."""

from __future__ import annotations

from urllib.parse import urlencode

import frappe
import requests


def _conf(key: str, fallback: str | None = None) -> str:
    settings = {}
    try:
        settings = frappe.get_site_config() or {}
    except Exception:
        settings = {}
    return str(settings.get(key) or frappe.conf.get(key) or fallback or "").strip()


def get_smartping_config() -> dict:
    base = (_conf("smartping_sms_base_url") or _conf("omni_sms_base_url")).rstrip("/")
    username = _conf("smartping_sms_username") or _conf("omni_sms_username")
    password = _conf("smartping_sms_password") or _conf("omni_sms_password")
    sender = _conf("smartping_sms_from") or _conf("omni_sms_from")
    template_id = _conf("smartping_sms_template_id") or _conf("omni_sms_template_id")
    text_template = (
        _conf("smartping_sms_text_template")
        or _conf("omni_sms_text_template")
        or _conf("sms_otp_text_template")
    )
    return {
        "base_url": base,
        "username": username,
        "password": password,
        "from": sender,
        "template_id": template_id,
        "dlt_content_id": _conf("smartping_sms_dlt_content_id") or _conf("omni_sms_dlt_content_id"),
        "pe_id": _conf("smartping_sms_pe_id") or _conf("omni_sms_pe_id"),
        "unicode": (_conf("smartping_sms_unicode") or "false").lower() == "true",
        "text_template": text_template,
        "enabled": bool(base and username and password and sender and template_id and text_template),
    }


def render_otp_text(otp: str, template: str) -> str:
    return template.replace("{otp}", otp)


def send_otp_sms(phone: str, otp: str) -> dict:
    config = get_smartping_config()
    if not config["enabled"]:
        return {"ok": False, "reason": "not_configured"}

    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        msisdn = digits
    elif len(digits) == 10:
        msisdn = "91" + digits
    else:
        msisdn = digits

    text = render_otp_text(otp, config["text_template"])
    payload = {
        "username": config["username"],
        "password": config["password"],
        "unicode": "true" if config["unicode"] else "false",
        "from": config["from"],
        "to": msisdn,
        "text": text,
        "templateId": config["template_id"],
    }
    if config["dlt_content_id"]:
        payload["dltContentId"] = config["dlt_content_id"]
    if config["pe_id"]:
        payload["dltPrincipalEntityId"] = config["pe_id"]

    url = f"{config['base_url']}/fe/api/v1/send"
    try:
        response = requests.post(
            url,
            data=urlencode(payload),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json, text/plain, */*",
            },
            timeout=20,
        )
        ok = response.ok
        return {"ok": ok, "status": response.status_code, "body": response.text[:500]}
    except Exception as exc:
        frappe.log_error(title="SmartPing SMS failed", message=str(exc))
        return {"ok": False, "reason": str(exc)}
