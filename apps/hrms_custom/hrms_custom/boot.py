import frappe

ADMIN_ONLY_MENU_NAMES = ("edit-sidebar", "help")
ADMIN_ONLY_MENU_LABELS = ("Edit Sidebar", "Help", "About", "Frappe Support")


def is_administrator_desk_user(user: str | None = None) -> bool:
	return (user or frappe.session.user) == "Administrator"


def is_restricted_desk_menu(item: dict | None) -> bool:
	if not item:
		return False
	if item.get("name") in ADMIN_ONLY_MENU_NAMES:
		return True
	label = item.get("label") or item.get("item_label")
	if label in ADMIN_ONLY_MENU_LABELS:
		return True
	if "show_about" in str(item.get("action") or ""):
		return True
	target = str(item.get("route") or item.get("url") or "")
	return "frappe.io/support" in target or "support.frappe" in target


def extend_bootinfo(bootinfo):
	bootinfo["hrms_administrator_desk"] = is_administrator_desk_user()
	bootinfo["hrms_admin_only_menu_names"] = list(ADMIN_ONLY_MENU_NAMES)
	bootinfo["hrms_admin_only_menu_labels"] = list(ADMIN_ONLY_MENU_LABELS)
