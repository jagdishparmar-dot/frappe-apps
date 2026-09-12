from __future__ import annotations

import frappe


def execute(filters: dict | None = None):
    filters = filters or {}
    doctype = filters.get("doctype") or "VB Invoice"
    if doctype not in ("VB Invoice", "VB Vendor", "VB Agreement"):
        frappe.throw("Choose VB Invoice, VB Vendor, or VB Agreement.")
    title_map = {
        "VB Invoice": "invoice_number",
        "VB Vendor": "vendor_name",
        "VB Agreement": "agreement_type",
    }
    title_field = title_map[doctype]
    columns = [
        {"label": "Doctype", "fieldname": "doctype", "fieldtype": "Data", "width": 120},
        {"label": "Name", "fieldname": "name", "fieldtype": "Link", "options": doctype, "width": 160},
        {"label": "Title", "fieldname": "title", "fieldtype": "Data", "width": 200},
        {"label": "Archived At", "fieldname": "archived_at", "fieldtype": "Datetime", "width": 160},
        {"label": "Remarks", "fieldname": "deletion_remarks", "fieldtype": "Data", "width": 280},
    ]
    rows = frappe.get_all(
        doctype,
        filters={"archived": 1},
        fields=["name", title_field, "archived_at", "deletion_remarks"],
        order_by="archived_at desc",
        limit=2000,
    )
    data = []
    for row in rows:
        data.append(
            {
                "doctype": doctype,
                "name": row.name,
                "title": row.get(title_field),
                "archived_at": row.archived_at,
                "deletion_remarks": row.deletion_remarks,
            }
        )
    return columns, data
