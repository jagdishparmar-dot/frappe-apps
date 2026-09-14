import frappe

from hr_portal.constants import DIRECTORY_ROLES
from hr_portal.services.dashboard_service import build_dashboard_snapshot
from hr_portal.utils import require_login, require_roles


@frappe.whitelist()
def get_dashboard_snapshot() -> dict:
	require_login()
	require_roles(*DIRECTORY_ROLES)
	return build_dashboard_snapshot()
