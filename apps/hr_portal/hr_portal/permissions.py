import frappe

from hr_portal.constants import (
	DIRECTORY_ROLES,
	EMPLOYEE_WRITE_ROLES,
	HR_REPORTING_MANAGER,
	PAYROLL_ADMIN_ROLES,
	SYSTEM_MANAGER,
)


def _roles(user: str | None = None) -> set[str]:
	return set(frappe.get_roles(user or frappe.session.user))


def is_staff(user: str | None = None) -> bool:
	return bool(_roles(user).intersection(DIRECTORY_ROLES))


def get_employee_name(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return None
	return frappe.db.get_value("HR Employee", {"user": user}, "name")


def employee_query(user: str | None = None) -> str:
	"""List filter for HR Employee. System/HR staff see all; others see own (+ reports)."""
	user = user or frappe.session.user
	if user == "Administrator" or SYSTEM_MANAGER in _roles(user) or is_staff(user):
		return ""

	name = get_employee_name(user)
	if not name:
		return "1=0"

	conditions = [f"`tabHR Employee`.user = {frappe.db.escape(user)}"]
	if HR_REPORTING_MANAGER in _roles(user):
		conditions.append(f"`tabHR Employee`.reports_to = {frappe.db.escape(name)}")
	return "(" + " OR ".join(conditions) + ")"


def employee_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator" or SYSTEM_MANAGER in _roles(user):
		return True

	roles = _roles(user)

	if ptype in ("create", "delete", "cancel"):
		return bool(roles.intersection(EMPLOYEE_WRITE_ROLES))

	if ptype == "write" and roles.intersection(EMPLOYEE_WRITE_ROLES):
		return True

	if ptype == "read" and is_staff(user):
		return True

	doc_user = doc.get("user") if hasattr(doc, "get") else getattr(doc, "user", None)
	if doc_user == user and ptype in ("read", "write"):
		return True

	if HR_REPORTING_MANAGER in roles and ptype == "read":
		manager_name = get_employee_name(user)
		reports_to = doc.get("reports_to") if hasattr(doc, "get") else getattr(doc, "reports_to", None)
		if manager_name and reports_to == manager_name:
			return True

	return False


def document_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or SYSTEM_MANAGER in _roles(user) or is_staff(user):
		return ""
	name = get_employee_name(user)
	if not name:
		return "1=0"
	conditions = [f"`tabHR Employee Document`.employee = {frappe.db.escape(name)}"]
	if HR_REPORTING_MANAGER in _roles(user):
		reports = frappe.get_all("HR Employee", filters={"reports_to": name}, pluck="name")
		if reports:
			quoted = ", ".join(frappe.db.escape(n) for n in reports)
			conditions.append(f"`tabHR Employee Document`.employee in ({quoted})")
	return "(" + " OR ".join(conditions) + ")"


def attendance_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or SYSTEM_MANAGER in _roles(user) or is_staff(user):
		return ""
	name = get_employee_name(user)
	if not name:
		return "1=0"
	conditions = [f"`tabHR Attendance`.employee = {frappe.db.escape(name)}"]
	if HR_REPORTING_MANAGER in _roles(user):
		reports = frappe.get_all("HR Employee", filters={"reports_to": name}, pluck="name")
		if reports:
			quoted = ", ".join(frappe.db.escape(n) for n in reports)
			conditions.append(f"`tabHR Attendance`.employee in ({quoted})")
	return "(" + " OR ".join(conditions) + ")"


def attendance_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator" or SYSTEM_MANAGER in _roles(user):
		return True
	if ptype in ("create", "delete", "cancel") and _roles(user).intersection(EMPLOYEE_WRITE_ROLES):
		return True
	if ptype == "read" and is_staff(user):
		return True
	own = get_employee_name(user)
	employee = doc.get("employee") if hasattr(doc, "get") else getattr(doc, "employee", None)
	if own and employee == own and ptype in ("read", "write", "create"):
		return True
	if HR_REPORTING_MANAGER in _roles(user) and ptype == "read" and own and employee:
		reports_to = frappe.db.get_value("HR Employee", employee, "reports_to")
		if reports_to == own:
			return True
	return False


def regularization_query(user: str | None = None) -> str:
	return attendance_query(user)


def regularization_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	return attendance_has_permission(doc, ptype, user, debug)


def _employee_scoped_query(doctype: str, user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or SYSTEM_MANAGER in _roles(user) or is_staff(user):
		return ""
	name = get_employee_name(user)
	if not name:
		return "1=0"
	conditions = [f"`tab{doctype}`.employee = {frappe.db.escape(name)}"]
	if HR_REPORTING_MANAGER in _roles(user):
		reports = frappe.get_all("HR Employee", filters={"reports_to": name}, pluck="name")
		if reports:
			quoted = ", ".join(frappe.db.escape(n) for n in reports)
			conditions.append(f"`tab{doctype}`.employee in ({quoted})")
	return "(" + " OR ".join(conditions) + ")"


def leave_request_query(user: str | None = None) -> str:
	return _employee_scoped_query("HR Leave Request", user)


def leave_request_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	return attendance_has_permission(doc, ptype, user, debug)


def leave_balance_query(user: str | None = None) -> str:
	return _employee_scoped_query("HR Leave Balance", user)


def leave_balance_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	return attendance_has_permission(doc, ptype, user, debug)


def shift_change_query(user: str | None = None) -> str:
	return _employee_scoped_query("HR Shift Change Request", user)


def shift_change_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	return attendance_has_permission(doc, ptype, user, debug)


def is_payroll_admin(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(_roles(user).intersection(PAYROLL_ADMIN_ROLES))


def payroll_admin_only(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator" or is_payroll_admin(user):
		return True
	return False


def payslip_query(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user == "Administrator" or is_payroll_admin(user):
		return ""
	name = get_employee_name(user)
	if not name:
		return "1=0"
	return f"`tabHR Payslip`.employee = {frappe.db.escape(name)}"


def payslip_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator" or is_payroll_admin(user):
		return True
	if ptype != "read":
		return False
	own = get_employee_name(user)
	employee = doc.get("employee") if hasattr(doc, "get") else getattr(doc, "employee", None)
	return bool(own and employee == own)


def audit_log_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	return payroll_admin_only(doc, ptype, user, debug)


def document_has_permission(doc, ptype: str = "read", user: str | None = None, debug: bool = False) -> bool:
	user = user or frappe.session.user
	if not user or user == "Guest":
		return False
	if user == "Administrator" or SYSTEM_MANAGER in _roles(user):
		return True

	roles = _roles(user)
	if ptype in ("create", "write", "delete") and roles.intersection(EMPLOYEE_WRITE_ROLES):
		return True
	if ptype == "read" and is_staff(user):
		return True

	own = get_employee_name(user)
	employee = doc.get("employee") if hasattr(doc, "get") else getattr(doc, "employee", None)
	if own and employee == own and ptype in ("read", "write", "create"):
		return True

	if HR_REPORTING_MANAGER in roles and ptype == "read" and own and employee:
		reports_to = frappe.db.get_value("HR Employee", employee, "reports_to")
		if reports_to == own:
			return True

	return False
