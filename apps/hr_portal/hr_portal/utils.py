import frappe
from frappe import _

from hr_portal.constants import EMPLOYEE_WRITE_ROLES, SYSTEM_MANAGER


def require_login() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Not logged in"), frappe.AuthenticationError)
	return user


def require_roles(*roles: str) -> None:
	require_login()
	if frappe.session.user == "Administrator":
		return
	current = set(frappe.get_roles())
	if SYSTEM_MANAGER in current:
		return
	if not current.intersection(roles):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def require_employee_write() -> None:
	require_roles(*EMPLOYEE_WRITE_ROLES)


def split_name(full_name: str) -> tuple[str, str]:
	parts = (full_name or "").strip().split(None, 1)
	if not parts:
		return "Employee", ""
	if len(parts) == 1:
		return parts[0], ""
	return parts[0], parts[1]


def newline_list(value: str | None) -> list[str]:
	if not value:
		return []
	seen: list[str] = []
	for line in value.splitlines():
		item = line.strip()
		if item and item not in seen:
			seen.append(item)
	return seen


def as_bool(value) -> bool:
	if isinstance(value, bool):
		return value
	if value in (None, "", 0, "0", "false", "False"):
		return False
	return True
