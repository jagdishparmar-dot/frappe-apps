from __future__ import annotations

import frappe


def execute(filters: dict | None = None):
    filters = filters or {}
    statuses = filters.get("status")
    if statuses:
        if isinstance(statuses, str):
            statuses = [statuses]
    else:
        statuses = ["Hold", "Rejected", "Paid"]
    columns = [
        {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "VB Invoice", "width": 140},
        {"label": "Number", "fieldname": "invoice_number", "fieldtype": "Data", "width": 140},
        {"label": "Vendor", "fieldname": "vendor", "fieldtype": "Link", "options": "VB Vendor", "width": 140},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 90},
        {"label": "Payment", "fieldname": "payment_status", "fieldtype": "Data", "width": 90},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 110},
        {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 220},
        {"label": "Payment Remarks", "fieldname": "payment_remarks", "fieldtype": "Data", "width": 220},
        {"label": "Date", "fieldname": "invoice_date", "fieldtype": "Date", "width": 110},
    ]
    rows = frappe.get_all(
        "VB Invoice",
        filters={"status": ["in", statuses], "archived": 0},
        fields=[
            "name",
            "invoice_number",
            "vendor",
            "status",
            "payment_status",
            "amount",
            "remarks",
            "payment_remarks",
            "invoice_date",
        ],
        order_by="modified desc",
        limit=2000,
    )
    return columns, rows
