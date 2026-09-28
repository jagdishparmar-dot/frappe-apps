import frappe

from hrms_custom.api.response import ApiError

# Joiners who may use the app before they become Active (they can only reach onboarding screens).
ONBOARDING_LOGIN_STATUSES = ("Invited", "Pending Verification")


def can_log_in(status: str | None, onboarding_status: str | None) -> bool:
	return status == "Active" or onboarding_status in ONBOARDING_LOGIN_STATUSES


def get_session_employee(
	fields: tuple[str, ...] = ("name", "employee_name", "company"), allow_onboarding: bool = False
) -> frappe._dict:
	"""Resolve the Employee for the logged-in user. The client never gets to choose who it is.

	By default only Active employees pass; `allow_onboarding` also admits invited joiners.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		raise ApiError("Please log in to continue", 401)

	employee = frappe.db.get_value(
		"Employee",
		{"user_id": user},
		list(dict.fromkeys([*fields, "status", "onboarding_status"])),
		as_dict=True,
	)
	if employee and employee.status == "Active":
		return employee
	if employee and allow_onboarding and employee.onboarding_status in ONBOARDING_LOGIN_STATUSES:
		return employee
	if employee and employee.onboarding_status in ONBOARDING_LOGIN_STATUSES:
		raise ApiError("Please complete your onboarding first", 403)
	raise ApiError("No active employee record is linked to your account. Please contact HR.", 403)
