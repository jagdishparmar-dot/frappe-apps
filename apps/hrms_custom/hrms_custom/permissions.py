import frappe

HR_ROLES = ("System Manager", "HR Admin", "HR Executive")


def is_hr(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user == "Administrator" or bool(set(HR_ROLES) & set(frappe.get_roles(user)))
