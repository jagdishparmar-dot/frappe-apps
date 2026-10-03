import os

import frappe
from frappe.modules.import_file import import_file_by_path

# (role, desk_access)
CUSTOM_ROLES = (
	("HR Admin", 1),
	("HR Executive", 1),
	("Manager", 1),
	("Employee", 1),
)

APP_ROLES = {"System Manager", "HR Admin", "HR Executive", "Manager", "Employee"}


def before_install():
	# Roles must exist before our doctypes (whose DocPerms reference them) are synced.
	create_roles()


def after_install():
	after_migrate()


def after_migrate():
	create_roles()
	sync_standard_navigation()
	seed_shift_types()


# Company is left empty so a new site can install before any company exists.
# Existing rows are not updated on migrate (insert-only when the name is missing).
DEFAULT_SHIFT_TYPES = (
	{
		"shift_name": "General",
		"start_time": "10:00:00",
		"end_time": "18:30:00",
		"grace_minutes": 15,
		"early_exit_grace_minutes": 0,
		"minimum_hours_present": 4.5,
		"minimum_hours_half_day": 4,
		"color": "#1F5EFF",
	},
	{
		"shift_name": "Standard Day",
		"start_time": "09:00:00",
		"end_time": "18:00:00",
		"grace_minutes": 15,
		"early_exit_grace_minutes": 10,
		"minimum_hours_present": 8,
		"minimum_hours_half_day": 4,
		"color": "#0EA5E9",
	},
	{
		"shift_name": "Overnight",
		"start_time": "22:00:00",
		"end_time": "06:00:00",
		"grace_minutes": 15,
		"early_exit_grace_minutes": 10,
		"minimum_hours_present": 7,
		"minimum_hours_half_day": 4,
		"color": "#6366F1",
	},
	{
		"shift_name": "12 Hour Day",
		"start_time": "08:00:00",
		"end_time": "20:00:00",
		"grace_minutes": 15,
		"early_exit_grace_minutes": 10,
		"minimum_hours_present": 11,
		"minimum_hours_half_day": 6,
		"color": "#22C55E",
	},
	{
		"shift_name": "12 Hour Night",
		"start_time": "20:00:00",
		"end_time": "08:00:00",
		"grace_minutes": 15,
		"early_exit_grace_minutes": 10,
		"minimum_hours_present": 11,
		"minimum_hours_half_day": 6,
		"color": "#A855F7",
	},
)


def seed_shift_types():
	for row in DEFAULT_SHIFT_TYPES:
		if frappe.db.exists("Shift Type", row["shift_name"]):
			continue
		frappe.get_doc({"doctype": "Shift Type", "is_active": 1, **row}).insert(ignore_permissions=True)


def sync_standard_navigation():
	"""Re-import the HRMS workspace and sidebar so new task links always appear.

	Frappe skips a standard Workspace Sidebar when the site's `modified` is newer than
	the file. That left Shifts and Documents missing after earlier rows.
	"""
	paths = [
		frappe.get_app_path("hrms_custom", "workspace_sidebar", "hrms.json"),
		# Empty module sidebar: Frappe auto-builds one named after the module when missing.
		frappe.get_app_path("hrms_custom", "workspace_sidebar", "hrms_custom.json"),
		frappe.get_app_path("hrms_custom", "hrms_custom", "workspace", "hrms", "hrms.json"),
	]
	number_card_root = frappe.get_app_path("hrms_custom", "hrms_custom", "number_card")
	if os.path.isdir(number_card_root):
		for name in os.listdir(number_card_root):
			path = os.path.join(number_card_root, name, f"{name}.json")
			if os.path.exists(path):
				paths.append(path)
	for path in paths:
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True)


def create_roles():
	for role, desk_access in CUSTOM_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": desk_access}).insert(
				ignore_permissions=True
			)


def has_app_permission() -> bool:
	"""Show the HRMS tile on the apps screen to HR staff, managers, and employees."""
	if frappe.session.user == "Administrator":
		return True
	return bool(APP_ROLES & set(frappe.get_roles()))
