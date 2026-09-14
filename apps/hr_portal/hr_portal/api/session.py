import frappe
from frappe import _

from hr_portal.constants import APP_ROLES, HR_EMPLOYEE
from hr_portal.permissions import get_employee_name


@frappe.whitelist(allow_guest=True)
def ping() -> str:
	return "pong"


def check_app_permission() -> bool:
	if frappe.session.user == "Administrator":
		return True
	return bool(set(frappe.get_roles()).intersection(APP_ROLES))


@frappe.whitelist()
def get_session() -> dict:
	if frappe.session.user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)

	roles = frappe.get_roles()
	employee_name = get_employee_name()
	employee = None
	if employee_name:
		employee = frappe.db.get_value(
			"HR Employee",
			employee_name,
			[
				"name",
				"employee_code",
				"employee_name",
				"email",
				"phone",
				"status",
				"portal_role",
				"must_change_password",
				"department",
				"designation",
				"employment_type",
				"attendance_policy",
				"primary_site",
				"default_shift",
				"image",
			],
			as_dict=True,
		)

	settings = frappe.get_single("HR Settings")
	return {
		"user": frappe.session.user,
		"full_name": frappe.db.get_value("User", frappe.session.user, "full_name"),
		"roles": roles,
		"is_employee_only": HR_EMPLOYEE in roles
		and not any(r in roles for r in ("HR Admin", "HR Manager", "HR Payroll Admin", "HR Reporting Manager", "System Manager")),
		"employee": employee,
		"must_change_password": bool(employee and employee.must_change_password),
		"settings": {
			"company_name": settings.company_name,
			"primary_color": settings.primary_color,
			"brand_logo": settings.brand_logo,
			"timezone": settings.timezone,
			"enabled": bool(settings.enabled),
		},
	}
