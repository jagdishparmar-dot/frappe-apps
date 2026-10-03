"""Shift types, employee calendar, and the monthly roster grid (spec section 9)."""

import frappe
from frappe.utils import cint, flt, get_time, getdate

from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import get_session_employee
from hrms_custom.permissions import is_hr
from hrms_custom.utils.shifts import (
	ROSTER_WEEK_OFF,
	build_calendar,
	build_roster,
	parse_entries,
	shift_type_dict,
)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_shift_types(include_inactive=None):
	"""Active shift types (HR may pass include_inactive=1 to see all)."""
	filters = {}
	if not (is_hr() and cint(include_inactive)):
		filters["is_active"] = 1
	names = frappe.get_all("Shift Type", filters=filters, pluck="name", order_by="shift_name asc")
	return {"shift_types": [shift_type_dict(frappe.get_doc("Shift Type", name)) for name in names]}


@frappe.whitelist(methods=["POST"])
@api_endpoint
def create_shift_type(
	shift_name=None,
	start_time=None,
	end_time=None,
	grace_minutes=0,
	early_exit_grace_minutes=0,
	working_hours=None,
	minimum_hours_present=None,
	minimum_hours_half_day=None,
	allow_flexible_hours=0,
	color=None,
	location=None,
	company=None,
	holiday_list=None,
	is_active=1,
):
	"""HR: define a shift type (start/end, grace, optional location and holiday list)."""
	if not is_hr():
		raise ApiError("Only HR can create shift types", 403)
	if not shift_name or not start_time or not end_time:
		raise ApiError("Shift name, start time and end time are required", 400)
	if frappe.db.exists("Shift Type", shift_name):
		raise ApiError(f"Shift type {shift_name} already exists", 409)
	doc = frappe.get_doc(
		{
			"doctype": "Shift Type",
			"shift_name": shift_name,
			"start_time": get_time(start_time),
			"end_time": get_time(end_time),
			"grace_minutes": cint(grace_minutes),
			"early_exit_grace_minutes": cint(early_exit_grace_minutes),
			"working_hours": flt(working_hours) if working_hours not in (None, "") else None,
			"minimum_hours_present": flt(minimum_hours_present) if minimum_hours_present not in (None, "") else None,
			"minimum_hours_half_day": flt(minimum_hours_half_day) if minimum_hours_half_day not in (None, "") else None,
			"allow_flexible_hours": cint(allow_flexible_hours),
			"color": color or "#1F5EFF",
			"location": location,
			"company": company,
			"holiday_list": holiday_list,
			"is_active": cint(is_active),
		}
	).insert()
	return success(shift_type_dict(doc), "Shift type created")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def my_shift_calendar(month=None):
	"""Day-keyed map of the logged-in employee's shifts and holidays for `month` (YYYY-MM)."""
	employee = get_session_employee(("name", "company"))
	return build_calendar(employee.name, employee.company, month)


@frappe.whitelist(methods=["GET", "POST"])
@api_endpoint
def get_roster(department=None, month=None, company=None):
	"""HR: employees × days grid for `month` (YYYY-MM), optional department/company filters."""
	if not is_hr():
		raise ApiError("Only HR can view the roster", 403)
	return build_roster(month, department=department or None, company=company or None)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def bulk_assign_roster(entries=None):
	"""HR: create/update/clear `Shift Roster` rows.

	Empty `shift_type` clears that day. Use `shift_type` = ROSTER_WEEK_OFF or `is_week_off` = 1
	for a scheduled weekly off.
	"""
	if not is_hr():
		raise ApiError("Only HR can update the roster", 403)
	try:
		rows = parse_entries(entries)
	except Exception:
		raise ApiError("entries must be a list of {employee, date, shift_type}", 400)
	if not rows:
		raise ApiError("No roster entries to save", 400)

	saved = 0
	cleared = 0
	for index, row in enumerate(rows, start=1):
		if not isinstance(row, dict):
			raise ApiError(f"Entry {index}: expected an object", 400)
		employee = (row.get("employee") or "").strip()
		raw_date = row.get("date")
		shift_type = (row.get("shift_type") or "").strip() or None
		location = (row.get("location") or "").strip() or None
		week_off = cint(row.get("is_week_off")) or shift_type == ROSTER_WEEK_OFF
		if week_off:
			shift_type = None
			location = None
		if not employee or not raw_date:
			raise ApiError(f"Entry {index}: employee and date are required", 400)
		try:
			day = getdate(raw_date)
		except Exception:
			raise ApiError(f"Entry {index}: date must be YYYY-MM-DD", 400)
		if not frappe.db.exists("Employee", employee):
			raise ApiError(f"Entry {index}: employee not found", 400)

		existing = frappe.db.get_value("Shift Roster", {"employee": employee, "date": day}, "name")
		if not shift_type and not week_off:
			if existing:
				frappe.delete_doc("Shift Roster", existing, ignore_permissions=True)
				cleared += 1
			continue
		if week_off:
			payload = {
				"employee": employee,
				"date": day,
				"shift_type": None,
				"location": None,
				"is_week_off": 1,
			}
		else:
			if not frappe.db.exists("Shift Type", shift_type):
				raise ApiError(f"Entry {index}: unknown shift type {shift_type}", 400)
			if location and not frappe.db.exists("Geofence Location", location):
				raise ApiError(f"Entry {index}: unknown location", 400)
			if not location:
				location = frappe.db.get_value("Shift Type", shift_type, "location")
			payload = {
				"employee": employee,
				"date": day,
				"shift_type": shift_type,
				"location": location,
				"is_week_off": 0,
			}

		if existing:
			doc = frappe.get_doc("Shift Roster", existing)
			doc.update(payload)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "Shift Roster", **payload}).insert(ignore_permissions=True)
		saved += 1

	return success({"saved": saved, "cleared": cleared}, "Roster saved")
