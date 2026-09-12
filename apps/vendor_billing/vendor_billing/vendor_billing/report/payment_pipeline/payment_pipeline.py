from __future__ import annotations

import frappe


def execute(filters: dict | None = None):
    columns = [
        {"label": "Payment Status", "fieldname": "payment_status", "fieldtype": "Data", "width": 140},
        {"label": "Count", "fieldname": "count", "fieldtype": "Int", "width": 90},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 140},
    ]
    rows = frappe.db.sql(
        """
        SELECT payment_status, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount
        FROM `tabVB Invoice`
        WHERE IFNULL(archived, 0) = 0
        GROUP BY payment_status
        ORDER BY FIELD(payment_status, 'none', 'approved', 'scheduled', 'paid')
        """,
        as_dict=True,
    )
    return columns, rows
