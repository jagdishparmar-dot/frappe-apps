import frappe


def after_install():
	_ensure_role()


def after_migrate():
	_ensure_role()


def _ensure_role():
	if not frappe.db.exists("Role", "Bench Manager"):
		doc = frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": "Bench Manager",
				"desk_access": 1,
				"is_custom": 1,
			}
		)
		doc.insert(ignore_permissions=True)
