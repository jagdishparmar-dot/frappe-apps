"""Return every Employee to Draft so master data can be edited again."""

import frappe


def execute():
	for name in frappe.get_all("Employee", filters={"docstatus": ["!=", 0]}, pluck="name"):
		frappe.db.set_value("Employee", name, "docstatus", 0, update_modified=False)
