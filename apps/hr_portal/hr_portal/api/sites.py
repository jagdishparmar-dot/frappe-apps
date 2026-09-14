import frappe

from hr_portal.constants import DIRECTORY_ROLES
from hr_portal.services.shift_service import get_live_presence as build_live_presence
from hr_portal.utils import require_roles


@frappe.whitelist()
def get_live_presence() -> dict:
	require_roles(*DIRECTORY_ROLES)
	return {"ok": True, **build_live_presence()}
