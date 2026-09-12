import frappe


def check_app_permission() -> bool:
    """Show the app on the desk Apps screen for any System Manager or VB* role."""
    if frappe.session.user == "Guest":
        return False
    if "System Manager" in frappe.get_roles():
        return True
    return any(role.startswith("VB ") and role != "VB Portal Gateway" for role in frappe.get_roles())
