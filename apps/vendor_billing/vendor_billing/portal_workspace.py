"""Phase 2 portal APIs: KYC, invoices, agreements, profile-change, notifications."""

from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from vendor_billing.document_flow import (
    assert_invoice_editable_by_vendor,
    submit_as_system,
    vendor_can_bill,
)
from vendor_billing.identity import find_vendor_duplicate
from vendor_billing.portal_auth import assert_vendor_owns, require_portal_session
from vendor_billing.portal_files import attach_bytes, file_payload, parse_upload, reattach
from vendor_billing.utils import normalize_phone

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
GST_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_ATTACHMENTS = 5


def _json(value):
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return frappe.parse_json(value) or {}
    return value


def _bank_public(value) -> dict:
    data = _json(value)
    return {
        "bankName": data.get("bank_name") or data.get("bankName") or "",
        "accountNumber": data.get("account_number") or data.get("accountNumber") or "",
        "ifscCode": data.get("ifsc_code") or data.get("ifscCode") or "",
        "beneficiaryName": data.get("beneficiary_name") or data.get("beneficiaryName") or "",
    }


def _parse_amount(value) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        frappe.throw(_("Amount must be a number greater than 0."))
    if amount <= 0:
        frappe.throw(_("Amount must be a number greater than 0."))
    return amount


def _iso(value) -> str:
    return str(value) if value else ""


def _vendor_doc(name: str):
    return frappe.get_doc("VB Vendor", name)


def _kyc_doc(vendor_name: str):
    name = frappe.db.get_value("VB Vendor KYC", {"vendor": vendor_name}, "name")
    if not name:
        doc = frappe.get_doc({"doctype": "VB Vendor KYC", "vendor": vendor_name, "kyc_status": "pending_submission"})
        doc.insert(ignore_permissions=True)
        return doc
    return frappe.get_doc("VB Vendor KYC", name)


def _kyc_details(kyc) -> dict:
    docs = {}
    for row in kyc.documents or []:
        docs[row.document_kind] = {
            "fileName": row.original_file_name or Path_name(row.attachment),
            "hasFile": bool(row.attachment),
            "documentKind": row.document_kind,
        }
    rejections = [
        {"remarks": r.remarks, "rejectedAt": _iso(r.rejected_at)} for r in (kyc.previous_rejections or [])
    ]
    return {
        "panNumber": kyc.pan_number or "",
        "companyType": kyc.company_type or "",
        "bankName": kyc.bank_name or "",
        "accountNumber": kyc.account_number or "",
        "ifscCode": kyc.ifsc_code or "",
        "beneficiaryName": kyc.beneficiary_name or "",
        "address": kyc.address or "",
        "kycDocName": (docs.get("kyc") or {}).get("fileName") or "",
        "panDocName": (docs.get("pan") or {}).get("fileName") or "",
        "gstDocName": (docs.get("gst") or {}).get("fileName") or "",
        "msmeDocName": (docs.get("msme") or {}).get("fileName") or "",
        "otherDocName": (docs.get("other") or {}).get("fileName") or "",
        "kycDocPath": "kyc" if docs.get("kyc") else "",
        "submittedAt": _iso(kyc.submitted_at),
        "verifiedAt": _iso(kyc.verified_at),
        "remarks": kyc.remarks or "",
        "previousRejections": rejections,
        "documents": docs,
    }


def Path_name(url: str | None) -> str:
    return (url or "").rstrip("/").split("/")[-1]


def serialize_vendor(vendor) -> dict:
    if isinstance(vendor, dict):
        vendor = _vendor_doc(vendor["name"])
    kyc = _kyc_doc(vendor.name)
    return {
        "id": vendor.name,
        "name": vendor.vendor_name,
        "email": vendor.email or "",
        "phone": vendor.phone or "",
        "token": vendor.token,
        "status": vendor.status or "active",
        "categories": [r.billing_category for r in (vendor.categories or [])],
        "gstNumber": vendor.gst_number or "",
        "states": [r.state for r in (vendor.states or [])],
        "hubs": [r.hub for r in (vendor.hubs or [])],
        "kycStatus": vendor.kyc_status or kyc.kyc_status,
        "kycDetails": _kyc_details(kyc),
        "archived": bool(vendor.archived),
    }


def serialize_invoice(inv) -> dict:
    if isinstance(inv, str):
        inv = frappe.get_doc("VB Invoice", inv)
    hub_name = ""
    if inv.hub:
        hub_name = frappe.db.get_value("VB Hub", inv.hub, "hub_name") or inv.hub
    attachments = []
    for row in inv.attachments or []:
        attachments.append(
            {
                "id": row.name,
                "invoiceId": inv.name,
                "fileName": row.label or Path_name(row.attachment),
                "fileType": "",
                "uploadedAt": _iso(inv.uploaded_at),
                "label": row.label or "",
            }
        )
    return {
        "id": inv.name,
        "category": inv.billing_category or "",
        "invoiceNumber": inv.invoice_number or "",
        "documentType": inv.document_type or "invoice",
        "linkedInvoiceId": inv.linked_invoice or "",
        "poNumber": inv.po_number or "",
        "grnNumber": inv.grn_number or "",
        "amount": float(inv.amount or 0),
        "date": _iso(inv.invoice_date)[:10],
        "dueDate": _iso(inv.due_date)[:10],
        "fileName": Path_name(inv.invoice_file),
        "uploadedAt": _iso(inv.uploaded_at),
        "status": inv.status or "Pending",
        "paymentStatus": inv.payment_status or "none",
        "scheduledPayDate": _iso(inv.scheduled_pay_date)[:10],
        "paidDate": _iso(inv.paid_date)[:10],
        "paymentReference": inv.payment_reference or "",
        "paymentRemarks": inv.payment_remarks or "",
        "remarks": inv.remarks or "",
        "state": inv.state or "",
        "hubId": inv.hub or "",
        "hubName": hub_name,
        "hardCopySubmittedTo": inv.hard_copy_submitted_to or "",
        "hardCopySubmissionDate": _iso(inv.hard_copy_submission_date)[:10],
        "attachments": attachments,
        "docstatus": int(inv.docstatus or 0),
        "editable": int(inv.docstatus or 0) == 0,
    }


def serialize_hub(row) -> dict:
    return {
        "id": row.name,
        "name": row.hub_name,
        "code": row.code or row.name,
        "state": row.state or "",
        "stateCode": row.state_code or "",
        "address": row.address or "",
        "city": row.city or "",
        "pincode": row.pincode or "",
        "gstin": row.gstin or "",
        "billingAddress": row.billing_address or "",
    }


def serialize_company() -> dict:
    try:
        doc = frappe.get_single("VB Company Profile")
    except Exception:
        return {
            "legalName": "",
            "tradeName": "",
            "pan": "",
            "email": "",
            "phone": "",
            "registeredAddress": "",
            "registeredState": "",
            "registeredStateCode": "",
            "registeredGstin": "",
        }
    return {
        "legalName": doc.legal_name or "",
        "tradeName": doc.trade_name or "",
        "pan": doc.pan or "",
        "email": doc.email or "",
        "phone": doc.phone or "",
        "registeredAddress": doc.registered_address or "",
        "registeredState": doc.registered_state or "",
        "registeredStateCode": doc.registered_state_code or "",
        "registeredGstin": doc.registered_gstin or "",
    }


def company_profile() -> dict:
    return serialize_company()


def list_hubs_for_vendor(vendor) -> list[dict]:
    codes = [r.hub for r in (vendor.hubs or []) if r.hub]
    states = [r.state for r in (vendor.states or []) if r.state]
    filters = {}
    if codes:
        filters["name"] = ["in", codes]
    elif states:
        filters["state"] = ["in", states]
    else:
        return []
    rows = frappe.get_all(
        "VB Hub",
        filters=filters,
        fields=[
            "name",
            "hub_name",
            "code",
            "state",
            "state_code",
            "address",
            "city",
            "pincode",
            "gstin",
            "billing_address",
        ],
        limit=500,
        order_by="hub_name",
        ignore_permissions=True,
    )
    return [serialize_hub(r) for r in rows]


def list_invoices_for_vendor(vendor_name: str) -> list[dict]:
    fields = ["name", "docstatus"]
    if frappe.get_meta("VB Invoice").has_field("amended_from"):
        fields.append("amended_from")
    rows = frappe.get_all(
        "VB Invoice",
        filters={"vendor": vendor_name, "archived": 0},
        fields=fields,
        order_by="creation desc",
        limit=100,
        ignore_permissions=True,
    )
    superseded = {row.amended_from for row in rows if row.get("amended_from")}
    names = [row.name for row in rows if row.name not in superseded]
    return [serialize_invoice(n) for n in names]


def full_payload(vendor) -> dict:
    if isinstance(vendor, dict):
        vendor = _vendor_doc(vendor["name"])
    assigned = [r.billing_category for r in (vendor.categories or []) if r.billing_category]
    categories = assigned or frappe.get_all(
        "VB Billing Category",
        pluck="name",
        order_by="name",
        ignore_permissions=True,
    )
    return {
        "vendor": serialize_vendor(vendor),
        "invoices": list_invoices_for_vendor(vendor.name),
        "categories": categories,
        "hubs": list_hubs_for_vendor(vendor),
        "company": serialize_company(),
    }


def _replace_kyc_doc(kyc, kind: str, upload: dict | None) -> None:
    if not upload:
        return
    remaining = [r for r in (kyc.documents or []) if r.document_kind != kind]
    kyc.set("documents", [])
    for row in remaining:
        kyc.append(
            "documents",
            {
                "document_kind": row.document_kind,
                "attachment": row.attachment,
                "original_file_name": row.original_file_name,
            },
        )
    url = attach_bytes(upload["file_name"], upload["content"], "VB Vendor KYC", kyc.name)
    kyc.append(
        "documents",
        {"document_kind": kind, "attachment": url, "original_file_name": upload["file_name"]},
    )


def kyc_submit(token: str | None = None, **kwargs) -> dict:
    ctx = require_portal_session(token)
    vendor = _vendor_doc(ctx["vendor"].name)
    kyc = _kyc_doc(vendor.name)
    if kyc.kyc_status == "verified" or int(kyc.docstatus or 0) == 1:
        frappe.throw(_("KYC is already verified."), frappe.PermissionError)
    if kyc.kyc_status == "pending_verification":
        frappe.throw(_("KYC is already submitted for verification."))

    pan = (kwargs.get("panNumber") or "").strip().upper()
    company_type = (kwargs.get("companyType") or "").strip()
    bank_name = (kwargs.get("bankName") or "").strip()
    account = re.sub(r"\D", "", kwargs.get("accountNumber") or "")
    ifsc = (kwargs.get("ifscCode") or "").strip().upper()
    beneficiary = (kwargs.get("beneficiaryName") or "").strip()
    address = (kwargs.get("address") or "").strip()
    gst = (kwargs.get("gstNumber") or "").strip().upper()

    if not PAN_RE.match(pan):
        frappe.throw(_("Enter a valid PAN (e.g. ABCDE1234F)."))
    if not company_type or not bank_name or not beneficiary or not address:
        frappe.throw(_("Company type, bank name, beneficiary, and address are required."))
    if not (9 <= len(account) <= 18):
        frappe.throw(_("Account number must be 9–18 digits."))
    if not IFSC_RE.match(ifsc):
        frappe.throw(_("Enter a valid IFSC code."))
    if gst and not GST_RE.match(gst):
        frappe.throw(_("Enter a valid GSTIN or leave it blank."))
    if gst:
        dup = frappe.get_all(
            "VB Vendor", filters={"gst_number": gst, "archived": 0}, pluck="name", ignore_permissions=True
        )
        if any(n != vendor.name for n in dup):
            frappe.throw(_("This GSTIN is already registered to another vendor."))

    kyc_upload = parse_upload(kwargs.get("kycDoc") or kwargs.get("file"))
    has_primary = any(r.document_kind == "kyc" and r.attachment for r in (kyc.documents or []))
    if not kyc_upload and not has_primary:
        frappe.throw(_("Upload a cancelled cheque or KYC proof."))

    kyc.pan_number = pan
    kyc.company_type = company_type
    kyc.bank_name = bank_name
    kyc.account_number = account
    kyc.ifsc_code = ifsc
    kyc.beneficiary_name = beneficiary
    kyc.address = address
    kyc.remarks = None
    _replace_kyc_doc(kyc, "kyc", kyc_upload)
    _replace_kyc_doc(kyc, "pan", parse_upload(kwargs.get("panDoc")))
    _replace_kyc_doc(kyc, "gst", parse_upload(kwargs.get("gstDoc")))
    _replace_kyc_doc(kyc, "msme", parse_upload(kwargs.get("msmeDoc")))
    _replace_kyc_doc(kyc, "other", parse_upload(kwargs.get("otherDoc")))
    kyc.save(ignore_permissions=True)
    kyc.submit_for_review()
    vendor.reload()

    if gst != (vendor.gst_number or ""):
        vendor.gst_number = gst or None
        vendor.save(ignore_permissions=True)
        vendor.reload()
    message = (
        "KYC details resubmitted successfully!"
        if kyc.previous_rejections
        else "KYC details submitted successfully!"
    )
    return {"success": True, "message": message, "vendor": serialize_vendor(vendor)}


def kyc_file(
    token: str | None = None, vendor: str | None = None, docType: str | None = None, **_kwargs
) -> dict:
    ctx = require_portal_session(token)
    vendor_name = ctx["vendor"].name
    if vendor and vendor != vendor_name:
        frappe.throw(_("Forbidden"), frappe.PermissionError)
    kind = (docType or "kyc").strip().lower()
    if kind not in {"kyc", "pan", "gst", "msme", "other"}:
        frappe.throw(_("Unknown KYC document type."))
    kyc = _kyc_doc(vendor_name)
    row = next((r for r in (kyc.documents or []) if r.document_kind == kind and r.attachment), None)
    if not row:
        frappe.throw(_("File not found."), frappe.DoesNotExistError)
    return file_payload(row.attachment, row.original_file_name)


def invoice_upload(token: str | None = None, **kwargs) -> dict:
    ctx = require_portal_session(token)
    vendor = _vendor_doc(ctx["vendor"].name)
    vendor_can_bill(vendor)
    vendor_id = kwargs.get("vendorId")
    if vendor_id and vendor_id != vendor.name:
        frappe.throw(_("Forbidden"), frappe.PermissionError)

    upload = parse_upload(kwargs.get("invoiceFile") or kwargs.get("file"))
    if not upload:
        frappe.throw(_("Invoice file is required."))
    file_url = attach_bytes(upload["file_name"], upload["content"])

    supporting = kwargs.get("supportingDocs") or []
    if isinstance(supporting, str):
        supporting = frappe.parse_json(supporting) or []
    if isinstance(supporting, dict):
        supporting = [supporting]
    if len(supporting) > MAX_ATTACHMENTS:
        frappe.throw(_("At most {0} supporting documents are allowed.").format(MAX_ATTACHMENTS))

    invoice_number = (kwargs.get("invoiceNumber") or "").strip()
    if not invoice_number:
        frappe.throw(_("Invoice number is required."))
    invoice_date = kwargs.get("date") or kwargs.get("invoiceDate")
    if not invoice_date:
        frappe.throw(_("Invoice date is required."))
    category = kwargs.get("category") or kwargs.get("billingCategory")
    if not category:
        frappe.throw(_("Billing category is required."))

    amount_f = _parse_amount(kwargs.get("amount"))
    due = kwargs.get("dueDate")
    if due and invoice_date and getdate(due) < getdate(invoice_date):
        frappe.throw(_("Due date cannot be before invoice date."))

    doc = frappe.get_doc(
        {
            "doctype": "VB Invoice",
            "vendor": vendor.name,
            "document_type": kwargs.get("documentType") or "invoice",
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            "due_date": due or None,
            "amount": amount_f,
            "billing_category": category,
            "linked_invoice": kwargs.get("linkedInvoiceId") or None,
            "po_number": kwargs.get("poNumber"),
            "grn_number": kwargs.get("grnNumber"),
            "hub": kwargs.get("hubId") or None,
            "state": kwargs.get("state"),
            "invoice_file": file_url,
            "remarks": kwargs.get("remarks"),
            "hard_copy_submitted_to": kwargs.get("hardCopySubmittedTo"),
            "hard_copy_submission_date": kwargs.get("hardCopySubmissionDate") or None,
            "status": "Pending",
            "payment_status": "none",
        }
    )
    extra_urls = []
    for item in supporting:
        parsed = parse_upload(item, supporting=True)
        if not parsed:
            continue
        url = attach_bytes(parsed["file_name"], parsed["content"])
        extra_urls.append(url)
        doc.append("attachments", {"attachment": url, "label": parsed["file_name"]})
    doc.insert(ignore_permissions=True)
    reattach(file_url, "VB Invoice", doc.name)
    for url in extra_urls:
        reattach(url, "VB Invoice", doc.name)
    doc.reload()
    submit_as_system(doc)
    return {"message": "Invoice submitted for AP review.", "invoice": serialize_invoice(doc)}


def invoice_get(token: str | None = None, invoice: str | None = None, **_kwargs) -> dict:
    ctx = require_portal_session(token)
    vendor_name = ctx["vendor"].name
    if invoice:
        doc = frappe.get_doc("VB Invoice", invoice)
        assert_vendor_owns(doc.vendor, vendor_name)
        return {"invoice": serialize_invoice(doc)}
    return {"invoices": list_invoices_for_vendor(vendor_name)}


def invoice_update(token: str | None = None, invoice: str | None = None, **kwargs) -> dict:
    ctx = require_portal_session(token)
    if not invoice:
        frappe.throw(_("Invoice is required."))
    doc = frappe.get_doc("VB Invoice", invoice)
    assert_vendor_owns(doc.vendor, ctx["vendor"].name)
    assert_invoice_editable_by_vendor(doc)

    mapping = {
        "invoiceNumber": "invoice_number",
        "documentType": "document_type",
        "date": "invoice_date",
        "invoiceDate": "invoice_date",
        "dueDate": "due_date",
        "category": "billing_category",
        "linkedInvoiceId": "linked_invoice",
        "poNumber": "po_number",
        "grnNumber": "grn_number",
        "hubId": "hub",
        "state": "state",
        "remarks": "remarks",
        "hardCopySubmittedTo": "hard_copy_submitted_to",
        "hardCopySubmissionDate": "hard_copy_submission_date",
    }
    for src, dest in mapping.items():
        if src in kwargs and kwargs[src] not in (None, ""):
            doc.set(dest, kwargs[src])
    if kwargs.get("amount") not in (None, ""):
        doc.amount = _parse_amount(kwargs["amount"])
    if doc.due_date and doc.invoice_date and getdate(doc.due_date) < getdate(doc.invoice_date):
        frappe.throw(_("Due date cannot be before invoice date."))

    upload = parse_upload(kwargs.get("invoiceFile") or kwargs.get("file"))
    if upload:
        doc.invoice_file = attach_bytes(upload["file_name"], upload["content"], "VB Invoice", doc.name)

    supporting = kwargs.get("supportingDocs")
    if supporting:
        if isinstance(supporting, str):
            supporting = frappe.parse_json(supporting) or []
        if isinstance(supporting, dict):
            supporting = [supporting]
        if len(doc.attachments or []) + len(supporting) > MAX_ATTACHMENTS:
            frappe.throw(_("At most {0} supporting documents are allowed.").format(MAX_ATTACHMENTS))
        for item in supporting:
            parsed = parse_upload(item, supporting=True)
            if not parsed:
                continue
            url = attach_bytes(parsed["file_name"], parsed["content"], "VB Invoice", doc.name)
            doc.append("attachments", {"attachment": url, "label": parsed["file_name"]})

    doc.save(ignore_permissions=True)
    submit_as_system(doc)
    return {"message": "Invoice resubmitted for AP review.", "invoice": serialize_invoice(doc)}


def invoice_file(
    token: str | None = None,
    invoice: str | None = None,
    attachment: str | None = None,
    **_kwargs,
) -> dict:
    ctx = require_portal_session(token)
    if not invoice:
        frappe.throw(_("Invoice is required."))
    doc = frappe.get_doc("VB Invoice", invoice)
    assert_vendor_owns(doc.vendor, ctx["vendor"].name)
    if attachment:
        row = next((r for r in (doc.attachments or []) if r.name == attachment), None)
        if not row:
            frappe.throw(_("File not found."), frappe.DoesNotExistError)
        return file_payload(row.attachment, row.label)
    return file_payload(doc.invoice_file, Path_name(doc.invoice_file))


def agreement_file(
    token: str | None = None,
    agreement: str | None = None,
    **_kwargs,
) -> dict:
    ctx = require_portal_session(token)
    if not agreement:
        frappe.throw(_("Agreement is required."))
    doc = frappe.get_doc("VB Agreement", agreement)
    assert_vendor_owns(doc.vendor, ctx["vendor"].name)
    if int(doc.docstatus or 0) != 1:
        frappe.throw(_("Agreement is not issued."))
    return file_payload(doc.agreement_file, Path_name(doc.agreement_file))


def agreements(token: str | None = None, **_kwargs) -> dict:
    ctx = require_portal_session(token)
    names = frappe.get_all(
        "VB Agreement",
        filters={"vendor": ctx["vendor"].name, "archived": 0, "docstatus": 1},
        pluck="name",
        order_by="creation desc",
        limit=2000,
        ignore_permissions=True,
    )
    items = []
    for name in names:
        doc = frappe.get_doc("VB Agreement", name)
        items.append(
            {
                "id": doc.name,
                "vendorId": doc.vendor,
                "vendorName": ctx["vendor"].vendor_name,
                "agreementType": doc.agreement_type,
                "startDate": _iso(doc.start_date)[:10],
                "endDate": _iso(doc.end_date)[:10],
                "firstPartyName": doc.first_party_name or "",
                "secondPartyName": doc.second_party_name or "",
                "bothPartyName": doc.both_party_name or "",
                "fileName": Path_name(doc.agreement_file),
                "status": doc.status,
                "remarks": doc.remarks or "",
                "rateCard": [
                    {
                        "id": r.name,
                        "itemDescription": r.item_description,
                        "unit": r.unit or "",
                        "rate": float(r.rate or 0),
                        "billingFrequency": r.billing_frequency or "",
                        "remarks": r.remarks or "",
                        "sortOrder": r.sort_order or 0,
                    }
                    for r in (doc.rate_card_items or [])
                ],
                "uploadedBy": doc.uploaded_by or "",
                "createdAt": _iso(doc.creation),
                "updatedAt": _iso(doc.modified),
            }
        )
    return {"items": items}


def profile_change(
    token: str | None = None,
    action: str | None = None,
    field: str | None = None,
    newValue=None,
    page: int | str | None = 1,
    limit: int | str | None = 20,
    status: str | None = None,
    **_kwargs,
) -> dict:
    ctx = require_portal_session(token)
    vendor = _vendor_doc(ctx["vendor"].name)
    action = (action or "list").strip()
    if action == "create":
        if (vendor.kyc_status or "") != "verified":
            frappe.throw(_("KYC must be verified before requesting a profile change."))
        field_name = (field or "").strip()
        if field_name not in {"phone", "email", "bank"}:
            frappe.throw(_("Unknown profile field."))
        pending = frappe.db.exists(
            "VB Vendor Profile Change Request",
            {"vendor": vendor.name, "field_name": field_name, "status": "pending"},
        )
        if pending:
            frappe.throw(_("A pending request for this field already exists."))
        payload = _json(newValue)
        kyc = _kyc_doc(vendor.name)
        if field_name == "phone":
            phone = normalize_phone(payload.get("phone"))
            if len(phone) != 10:
                frappe.throw(_("Enter a valid 10-digit mobile number."))
            if phone == normalize_phone(vendor.phone):
                frappe.throw(_("New phone is the same as the current number."))
            dup = find_vendor_duplicate(phone, None, None, exclude=vendor.name)
            if dup:
                frappe.throw(_("This mobile number is already registered."))
            old = {"phone": vendor.phone}
            payload = {"phone": phone}
        elif field_name == "email":
            email = (payload.get("email") or "").strip()
            if not EMAIL_RE.match(email):
                frappe.throw(_("Enter a valid email address."))
            if email.lower() == (vendor.email or "").lower():
                frappe.throw(_("New email is the same as the current email."))
            old = {"email": vendor.email}
            payload = {"email": email}
        else:
            bank = {
                "bank_name": (payload.get("bankName") or payload.get("bank_name") or "").strip(),
                "account_number": re.sub(r"\D", "", payload.get("accountNumber") or payload.get("account_number") or ""),
                "ifsc_code": (payload.get("ifscCode") or payload.get("ifsc_code") or "").strip().upper(),
                "beneficiary_name": (payload.get("beneficiaryName") or payload.get("beneficiary_name") or "").strip(),
            }
            if not bank["bank_name"] or not bank["beneficiary_name"]:
                frappe.throw(_("Bank name and beneficiary are required."))
            if not (9 <= len(bank["account_number"]) <= 18) or not IFSC_RE.match(bank["ifsc_code"]):
                frappe.throw(_("Enter a valid account number and IFSC."))
            old = {
                "bank_name": kyc.bank_name,
                "account_number": kyc.account_number,
                "ifsc_code": kyc.ifsc_code,
                "beneficiary_name": kyc.beneficiary_name,
            }
            payload = bank
        doc = frappe.get_doc(
            {
                "doctype": "VB Vendor Profile Change Request",
                "vendor": vendor.name,
                "field_name": field_name,
                "old_value": old,
                "new_value": payload,
                "status": "pending",
            }
        )
        doc.insert(ignore_permissions=True)
        submit_as_system(doc)
        return {
            "message": "Profile change request submitted for admin approval.",
            "request": _serialize_profile_req(doc, vendor.vendor_name),
        }

    page_i = max(int(page or 1), 1)
    limit_i = min(max(int(limit or 20), 1), 100)
    filters = {"vendor": vendor.name}
    if status:
        filters["status"] = status
    total = frappe.db.count("VB Vendor Profile Change Request", filters)
    names = frappe.get_all(
        "VB Vendor Profile Change Request",
        filters=filters,
        pluck="name",
        order_by="creation desc",
        start=(page_i - 1) * limit_i,
        limit=limit_i,
        ignore_permissions=True,
    )
    items = [_serialize_profile_req(frappe.get_doc("VB Vendor Profile Change Request", n), vendor.vendor_name) for n in names]
    return {"items": items, "total": total, "page": page_i, "limit": limit_i}


def _serialize_profile_req(doc, vendor_name: str) -> dict:
    new_value = _json(doc.new_value)
    old_value = _json(doc.old_value)
    field = doc.field_name
    if field == "bank":
        new_value = _bank_public(new_value)
        old_value = _bank_public(old_value)
    return {
        "id": doc.name,
        "vendorId": doc.vendor,
        "field": field,
        "oldValue": old_value,
        "newValue": new_value,
        "status": doc.status,
        "reviewRemarks": doc.review_remarks or "",
        "reviewedBy": doc.reviewed_by or "",
        "reviewedAt": _iso(doc.reviewed_at),
        "createdAt": _iso(doc.creation),
        "vendorName": vendor_name,
    }


def notifications(
    token: str | None = None,
    page: int | str | None = 1,
    limit: int | str | None = 20,
    unreadOnly: int | str | bool | None = None,
    countOnly: int | str | bool | None = None,
    **_kwargs,
) -> dict:
    ctx = require_portal_session(token)
    vendor_name = ctx["vendor"].name
    filters: dict = {"recipient_type": "vendor", "recipient_id": vendor_name}
    unread_count = frappe.db.count("VB Notification", {**filters, "read_at": ["is", "not set"]})
    if str(countOnly) in {"1", "true", "True"}:
        return {"unreadCount": unread_count}
    if str(unreadOnly) in {"1", "true", "True"}:
        filters["read_at"] = ["is", "not set"]
    page_i = max(int(page or 1), 1)
    limit_i = min(max(int(limit or 20), 1), 50)
    total = frappe.db.count("VB Notification", filters)
    rows = frappe.get_all(
        "VB Notification",
        filters=filters,
        fields=["name", "recipient_type", "recipient_id", "title", "body", "link", "read_at", "creation"],
        order_by="creation desc",
        start=(page_i - 1) * limit_i,
        limit=limit_i,
        ignore_permissions=True,
    )
    items = [
        {
            "id": r.name,
            "recipientType": r.recipient_type,
            "recipientId": r.recipient_id,
            "title": r.title,
            "body": r.body or "",
            "link": r.link or "",
            "readAt": _iso(r.read_at),
            "createdAt": _iso(r.creation),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": page_i, "limit": limit_i, "unreadCount": unread_count}


def notification_read(
    token: str | None = None,
    notification: str | None = None,
    action: str | None = None,
    **_kwargs,
) -> dict:
    ctx = require_portal_session(token)
    vendor_name = ctx["vendor"].name
    if (action or "") == "read-all":
        names = frappe.get_all(
            "VB Notification",
            filters={"recipient_type": "vendor", "recipient_id": vendor_name, "read_at": ["is", "not set"]},
            pluck="name",
            ignore_permissions=True,
        )
        now = now_datetime()
        for name in names:
            frappe.db.set_value("VB Notification", name, "read_at", now, update_modified=False)
        return {"message": "All notifications marked as read."}
    if not notification:
        frappe.throw(_("Notification is required."))
    doc = frappe.get_doc("VB Notification", notification)
    if doc.recipient_type != "vendor" or doc.recipient_id != vendor_name:
        frappe.throw(_("Forbidden"), frappe.PermissionError)
    if not doc.read_at:
        doc.read_at = now_datetime()
        doc.save(ignore_permissions=True)
    return {"message": "Marked as read."}
