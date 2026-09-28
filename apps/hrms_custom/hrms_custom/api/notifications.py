"""Employee device tokens, notification preferences, and the in-app inbox."""

import frappe
from frappe.utils import cint, now_datetime

from hrms_custom.api.response import ApiError, api_endpoint
from hrms_custom.api.session import get_session_employee
from hrms_custom.utils.notify import notification_dict, preference_dict

PREFERENCE_FIELDS = ("notify_shift_start", "notify_shift_end", "notify_approvals")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_notification_preferences():
	employee = get_session_employee(("name", *PREFERENCE_FIELDS), allow_onboarding=True)
	return preference_dict(employee)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def update_notification_preferences(notify_shift_start=None, notify_shift_end=None, notify_approvals=None):
	"""Save channel toggles immediately. These are not HR-reviewed profile changes."""
	employee = get_session_employee(("name", *PREFERENCE_FIELDS), allow_onboarding=True)
	values = {}
	if notify_shift_start is not None:
		values["notify_shift_start"] = 1 if cint(notify_shift_start) else 0
	if notify_shift_end is not None:
		values["notify_shift_end"] = 1 if cint(notify_shift_end) else 0
	if notify_approvals is not None:
		values["notify_approvals"] = 1 if cint(notify_approvals) else 0
	if not values:
		raise ApiError("No preference changes", 400)
	frappe.db.set_value("Employee", employee.name, values)
	employee.update(values)
	return preference_dict(employee)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def register_device(fcm_token=None, platform=None, device_id=None):
	employee = get_session_employee(("name",), allow_onboarding=True)
	token = (fcm_token or "").strip()
	if not token:
		raise ApiError("fcm_token is required", 400)
	platform = (platform or "").strip().lower()
	if platform not in ("android", "ios", "web"):
		platform = "android"
	existing = frappe.db.get_value("Employee Device", {"fcm_token": token}, ["name", "employee"], as_dict=True)
	now = now_datetime()
	if existing:
		frappe.db.set_value(
			"Employee Device",
			existing.name,
			{"employee": employee.name, "platform": platform, "device_id": device_id, "last_seen": now},
		)
		return {"name": existing.name}
	doc = frappe.get_doc(
		{
			"doctype": "Employee Device",
			"employee": employee.name,
			"fcm_token": token,
			"platform": platform,
			"device_id": device_id,
			"last_seen": now,
		}
	).insert(ignore_permissions=True)
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
@api_endpoint
def unregister_device(fcm_token=None):
	employee = get_session_employee(("name",), allow_onboarding=True)
	token = (fcm_token or "").strip()
	if not token:
		raise ApiError("fcm_token is required", 400)
	name = frappe.db.get_value("Employee Device", {"fcm_token": token, "employee": employee.name}, "name")
	if not name:
		raise ApiError("Device is not registered for this employee", 403)
	frappe.delete_doc("Employee Device", name, force=True, ignore_permissions=True)
	return {"ok": True}


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_my_notifications(unread_only=0, limit=50):
	employee = get_session_employee(("name",), allow_onboarding=True)
	filters = {"employee": employee.name}
	if cint(unread_only):
		filters["read"] = 0
	names = frappe.get_all(
		"Employee Notification",
		filters=filters,
		pluck="name",
		order_by="creation desc",
		limit=min(cint(limit) or 50, 100),
		ignore_permissions=True,
	)
	rows = [notification_dict(frappe.get_doc("Employee Notification", name)) for name in names]
	unread = frappe.db.count("Employee Notification", {"employee": employee.name, "read": 0})
	return {"notifications": rows, "unread_count": unread}


@frappe.whitelist(methods=["POST"])
@api_endpoint
def mark_notifications_read(names=None, mark_all=0):
	employee = get_session_employee(("name",), allow_onboarding=True)
	if cint(mark_all):
		for name in frappe.get_all(
			"Employee Notification", filters={"employee": employee.name, "read": 0}, pluck="name"
		):
			frappe.db.set_value("Employee Notification", name, "read", 1)
		return {"ok": True}
	if isinstance(names, str):
		names = frappe.parse_json(names)
	if not isinstance(names, list) or not names:
		raise ApiError("names is required", 400)
	for name in names:
		owner = frappe.db.get_value("Employee Notification", name, "employee")
		if owner != employee.name:
			raise ApiError("You can only mark your own notifications", 403)
		frappe.db.set_value("Employee Notification", name, "read", 1)
	return {"ok": True}
