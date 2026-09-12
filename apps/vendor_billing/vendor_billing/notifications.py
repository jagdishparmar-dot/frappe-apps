from __future__ import annotations

import frappe

from vendor_billing.utils import write_audit

ADMIN_RECIPIENT = "admin"


def settings():
    if not frappe.db.exists("DocType", "VB Notification Settings"):
        return None
    try:
        return frappe.get_single("VB Notification Settings")
    except Exception:
        return None


def portal_origin() -> str:
    s = settings()
    origin = (s.portal_origin if s else None) or frappe.conf.get("vb_portal_origin") or ""
    return str(origin).rstrip("/")


def portal_url(token: str) -> str:
    origin = portal_origin() or "http://localhost:3000"
    return f"{origin}/portal/{token}"


def create_in_app(*, recipient_type: str, recipient_id: str, title: str, body: str, link: str | None = None):
    frappe.get_doc(
        {
            "doctype": "VB Notification",
            "recipient_type": recipient_type,
            "recipient_id": recipient_id,
            "title": title,
            "body": body,
            "link": link,
        }
    ).insert(ignore_permissions=True)


def send_mail(recipients: list[str] | str, subject: str, html: str) -> None:
    if not recipients:
        return
    try:
        frappe.sendmail(recipients=recipients, subject=subject, message=html, now=True)
    except Exception:
        frappe.log_error(title="VB email send failed")


def notify_invoice_uploaded(invoice) -> None:
    s = settings()
    vendor_name = frappe.db.get_value("VB Vendor", invoice.vendor, "vendor_name")
    create_in_app(
        recipient_type="admin",
        recipient_id=ADMIN_RECIPIENT,
        title=f"Invoice uploaded: {invoice.invoice_number}",
        body=f"{vendor_name} uploaded {invoice.invoice_number}",
        link=f"/app/vb-invoice/{invoice.name}",
    )
    if s and s.notify_company_on_invoice_upload:
        company = frappe.get_single("VB Company Profile") if frappe.db.exists("DocType", "VB Company Profile") else None
        to = company.email if company else None
        if to:
            send_mail(
                to,
                f"New invoice uploaded: {invoice.invoice_number}",
                f"<p>Vendor <b>{vendor_name}</b> submitted invoice <b>{invoice.invoice_number}</b> "
                f"({invoice.amount}).</p>",
            )


def notify_invoice_status_change(invoice) -> None:
    s = settings()
    vendor = frappe.get_cached_doc("VB Vendor", invoice.vendor)
    create_in_app(
        recipient_type="vendor",
        recipient_id=vendor.name,
        title=f"Invoice {invoice.invoice_number} updated",
        body=f"Status {invoice.status} / payment {invoice.payment_status}",
    )
    if s and s.notify_vendor_on_invoice_status_change and vendor.email:
        send_mail(
            vendor.email,
            f"Invoice {invoice.invoice_number} status updated",
            f"<p>Your invoice <b>{invoice.invoice_number}</b> is now "
            f"<b>{invoice.status}</b> (payment: {invoice.payment_status}).</p>",
        )


def notify_kyc_verified(vendor_name: str) -> None:
    s = settings()
    vendor = frappe.get_cached_doc("VB Vendor", vendor_name)
    create_in_app(
        recipient_type="vendor",
        recipient_id=vendor.name,
        title="KYC verified",
        body="Your KYC documents were verified. You can upload invoices.",
    )
    if s and s.notify_vendor_on_kyc_verified and vendor.email:
        send_mail(
            vendor.email,
            "KYC verified",
            f"<p>Hello {vendor.vendor_name}, your KYC has been verified.</p>",
        )


def notify_vendor_registered(vendor) -> None:
    s = settings()
    url = portal_url(vendor.token)
    create_in_app(
        recipient_type="vendor",
        recipient_id=vendor.name,
        title="Welcome to the vendor portal",
        body="Use your portal link to complete KYC and upload invoices.",
        link=url,
    )
    if s and s.notify_vendor_on_registration and vendor.email:
        send_mail(
            vendor.email,
            "Your vendor portal is ready",
            f"<p>Hello {vendor.vendor_name},</p>"
            f"<p>Use your secure portal: <a href=\"{url}\">{url}</a></p>",
        )
    write_audit(action="vendor.welcome_email", entity_type="VB Vendor", entity_id=vendor.name, actor_type="system")
