import frappe

from bench_control.services import bench_ops


def check_app_permission() -> bool:
	if frappe.session.user == "Guest":
		return False
	roles = set(frappe.get_roles())
	return "System Manager" in roles or "Bench Manager" in roles
