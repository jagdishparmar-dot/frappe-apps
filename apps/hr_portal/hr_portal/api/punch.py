import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from hr_portal.permissions import get_employee_name
from hr_portal.services.punch_service import process_punch as run_process_punch
from hr_portal.utils import require_login


@frappe.whitelist()
@rate_limit(limit=30, seconds=60, key="punch")
def process_punch(
	type: str,
	lat: float,
	long: float,
	accuracy: float = 0,
	device_id: str = "",
	timezone: str = "",
) -> dict:
	require_login()
	employee_name = get_employee_name()
	if not employee_name:
		frappe.throw(_("No employee record found"), frappe.PermissionError)

	punch_type = (type or "").strip().lower()
	if punch_type not in ("in", "out"):
		frappe.throw(_("Invalid punch type"))

	try:
		lat_f = float(lat)
		lon_f = float(long)
	except (TypeError, ValueError):
		frappe.throw(_("Invalid coordinates"))

	result = run_process_punch(
		employee_name,
		punch_type,  # type: ignore[arg-type]
		lat_f,
		lon_f,
		accuracy=float(accuracy or 0),
		device_id=str(device_id or ""),
		timezone=timezone or None,
	)
	return {"ok": True, **result}
