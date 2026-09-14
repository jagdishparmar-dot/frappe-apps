import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint
from frappe.utils.password import check_password, update_password

from hr_portal.permissions import get_employee_name


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=20, seconds=60 * 60)
def login(email: str, password: str) -> dict:
	email = (email or "").strip().lower()
	if not email or not password:
		frappe.throw(_("Email and password are required"))

	check_password(email, password)
	user_name = frappe.db.get_value("User", email, "name") or frappe.db.get_value("User", {"email": email}, "name")
	if not user_name:
		frappe.throw(_("Invalid login"))
	if not cint(frappe.db.get_value("User", user_name, "enabled")):
		frappe.throw(_("User is disabled"))

	frappe.set_user(user_name)
	user = frappe.get_doc("User", user_name)
	api_secret = frappe.generate_hash(length=15)
	if not user.api_key:
		user.api_key = frappe.generate_hash(length=15)
	user.api_secret = api_secret
	user.flags.ignore_permissions = True
	user.save()

	from hr_portal.api.session import get_session

	session = get_session()
	employee = session.get("employee") or {}
	settings = session.get("settings") or {}
	memberships = []
	if employee:
		memberships.append(
			{
				"employeeId": employee.get("name"),
				"companyId": "default",
				"companyName": settings.get("company_name") or "HR",
				"mustChangePassword": bool(employee.get("must_change_password")),
				"role": employee.get("portal_role") or "HR Employee",
			}
		)

	return {
		"ok": True,
		"api_key": user.api_key,
		"api_secret": api_secret,
		"user": {
			"$id": user.name,
			"id": user.name,
			"email": user.email or user.name,
			"name": user.full_name or user.first_name or user.name,
		},
		"memberships": memberships,
		"session": session,
	}


@frappe.whitelist()
@rate_limit(limit=10, seconds=60 * 60)
def change_password(current_password: str, new_password: str) -> dict:
	if frappe.session.user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)
	if not current_password or not new_password:
		frappe.throw(_("Current and new password are required"))
	if len(new_password) < 8:
		frappe.throw(_("Password must be at least 8 characters"))

	from frappe.utils.password import check_password

	check_password(frappe.session.user, current_password)
	update_password(frappe.session.user, new_password)

	employee_name = get_employee_name()
	if employee_name:
		frappe.db.set_value("HR Employee", employee_name, "must_change_password", 0)

	return {"ok": True}
