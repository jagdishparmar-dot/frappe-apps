"""Import hubs / vendors from JSON (ETL helper).

Usage (from bench):

    bench --site <site> execute vendor_billing.import_masters.import_hubs --kwargs "{'rows': [...]}"
    bench --site <site> execute vendor_billing.import_masters.import_vendors --kwargs "{'rows': [...]}"

Row shapes match the old Prisma models (id, name, code, phone, token, ...).
KYC files are Phase 4 — this only writes metadata.
"""

from __future__ import annotations

import frappe

from vendor_billing.utils import new_portal_token, normalize_phone


def import_hubs(rows: list[dict]) -> dict:
    created = updated = 0
    for row in rows:
        code = (row.get("code") or "").strip()
        if not code:
            continue
        payload = {
            "hub_name": row.get("name") or code,
            "code": code,
            "state": row.get("state") or "",
            "state_code": row.get("stateCode") or row.get("state_code"),
            "address": row.get("address") or "",
            "city": row.get("city") or "",
            "pincode": row.get("pincode") or "",
            "gstin": row.get("gstin"),
            "billing_address": row.get("billingAddress") or row.get("billing_address"),
            "legacy_id": row.get("id"),
        }
        if frappe.db.exists("VB Hub", code):
            doc = frappe.get_doc("VB Hub", code)
            doc.update(payload)
            doc.save(ignore_permissions=True)
            updated += 1
        else:
            frappe.get_doc({"doctype": "VB Hub", **payload}).insert(ignore_permissions=True)
            created += 1
    frappe.db.commit()
    return {"created": created, "updated": updated}


def import_vendors(rows: list[dict]) -> dict:
    created = updated = skipped = 0
    for row in rows:
        legacy_id = row.get("id")
        token = row.get("token") or new_portal_token()
        name = None
        if legacy_id:
            name = frappe.db.get_value("VB Vendor", {"legacy_id": legacy_id}, "name")
        if not name:
            name = frappe.db.get_value("VB Vendor", {"token": token}, "name")
        payload = {
            "vendor_name": row.get("name"),
            "email": row.get("email") or "",
            "phone": row.get("phone"),
            "phone_normalized": normalize_phone(row.get("phone")),
            "token": token,
            "status": row.get("status") or "active",
            "gst_number": row.get("gstNumber") or row.get("gst_number"),
            "kyc_status": row.get("kycStatus") or row.get("kyc_status") or "pending_submission",
            "archived": 1 if row.get("archived") else 0,
            "deletion_remarks": row.get("deletionRemarks"),
            "legacy_id": legacy_id,
        }
        hubs = row.get("hubIds") or row.get("hubs") or []
        categories = row.get("categories") or []
        states = row.get("states") or ([row["state"]] if row.get("state") else [])
        resolved_hubs = []
        for h in hubs:
            if frappe.db.exists("VB Hub", h):
                resolved_hubs.append({"hub": h})
            else:
                code = frappe.db.get_value("VB Hub", {"legacy_id": h}, "name")
                if code:
                    resolved_hubs.append({"hub": code})
        payload["hubs"] = resolved_hubs
        payload["categories"] = [
            {"billing_category": c} for c in categories if frappe.db.exists("VB Billing Category", c)
        ]
        payload["states"] = [{"state": s} for s in states if s]

        if name:
            doc = frappe.get_doc("VB Vendor", name)
            doc.update(payload)
            doc.save(ignore_permissions=True)
            updated += 1
        else:
            if not payload["vendor_name"] or not payload["phone"]:
                skipped += 1
                continue
            frappe.get_doc({"doctype": "VB Vendor", **payload}).insert(ignore_permissions=True)
            created += 1
    frappe.db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def import_company_profile(row: dict) -> None:
    doc = frappe.get_single("VB Company Profile")
    doc.legal_name = row.get("legalName") or row.get("legal_name")
    doc.trade_name = row.get("tradeName") or row.get("trade_name") or ""
    doc.pan = row.get("pan") or ""
    doc.email = row.get("email") or ""
    doc.phone = row.get("phone") or ""
    doc.registered_address = row.get("registeredAddress") or row.get("registered_address")
    doc.registered_state = row.get("registeredState") or row.get("registered_state")
    doc.registered_state_code = row.get("registeredStateCode") or row.get("registered_state_code") or ""
    doc.registered_gstin = row.get("registeredGstin") or row.get("registered_gstin")
    doc.save(ignore_permissions=True)
    frappe.db.commit()
