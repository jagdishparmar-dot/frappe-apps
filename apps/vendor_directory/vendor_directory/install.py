# Copyright (c) 2026, Vendor Directory and contributors
# For license information, please see license.txt

import frappe


def after_install():
	_ensure_roles()


def after_migrate():
	_ensure_roles()


def has_app_permission():
	"""Show Vendor Directory on the Desk apps screen for admin roles."""
	return bool(
		set(frappe.get_roles()).intersection(
			{"System Manager", "Vendor Manager", "Administrator"}
		)
	)


def _ensure_roles():
	for role_name in ("Vendor Manager", "Vendor Portal User", "Vendor User"):
		if not frappe.db.exists("Role", role_name):
			doc = frappe.get_doc({"doctype": "Role", "role_name": role_name})
			if role_name == "Vendor Portal User":
				doc.desk_access = 0
			doc.insert(ignore_permissions=True)
	# Prefer portal role without desk access
	if frappe.db.exists("Role", "Vendor Portal User"):
		frappe.db.set_value("Role", "Vendor Portal User", "desk_access", 0)
	frappe.db.commit()
