import frappe

from hr_portal.constants import HR_ROLES


def after_install() -> None:
	ensure_roles()
	ensure_hr_settings()


def after_migrate() -> None:
	ensure_roles()
	ensure_hr_settings()


def ensure_roles() -> None:
	for role_name in HR_ROLES:
		if frappe.db.exists("Role", role_name):
			role = frappe.get_doc("Role", role_name)
			if role.desk_access:
				role.desk_access = 0
				role.save(ignore_permissions=True)
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 0,
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)


def ensure_hr_settings() -> None:
	if not frappe.db.exists("DocType", "HR Settings"):
		return
	doc = frappe.get_single("HR Settings")
	dirty = False
	defaults = {
		"company_name": "My Company",
		"timezone": "Asia/Kolkata",
		"currency": "INR",
		"work_week": "Mon,Tue,Wed,Thu,Fri",
		"late_grace_minutes": 15,
		"employee_code_prefix": "EMP",
		"employee_code_padding": 4,
		"employee_code_next_sequence": 1,
		"employee_code_auto_generate": 1,
		"primary_color": "#1A3A6B",
		"email_sender_name": "HR Portal",
		"geofencing": 1,
		"enabled": 1,
		"departments": "Operations\nHR\nFinance\nSales",
		"designations": "Associate\nManager\nDirector",
	}
	for field, value in defaults.items():
		if not doc.get(field):
			doc.set(field, value)
			dirty = True
	if dirty:
		doc.save(ignore_permissions=True)
