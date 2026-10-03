"""Drop the report whose slash broke the Desk route."""

import frappe

OLD_NAME = "Late Coming / Early Going"


def execute():
	if frappe.db.exists("Report", OLD_NAME):
		frappe.delete_doc("Report", OLD_NAME, force=True, ignore_permissions=True)
