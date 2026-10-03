from datetime import datetime, timedelta

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime

from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import get_session_employee
from hrms_custom.permissions import is_hr
from hrms_custom.utils.geo import Geofence, resolve_geofence, validate_coordinates
from hrms_custom.utils.reports import (
	_load_checkins,
	_pair_punches,
	employee_month_attendance,
	live_attendance,
	log_search_window,
	shift_window,
)
from hrms_custom.utils.shifts import shift_for_day

PUNCH_TYPES = ("IN", "OUT")
POLICY_REJECT = "Reject"
POLICY_FLAG = "Flag"


@frappe.whitelist(methods=["POST"])
@api_endpoint
def punch(latitude=None, longitude=None, punch_type=None, device_id=None, captured_at=None):
	"""Record an IN/OUT punch for the logged-in employee after server-side geofence validation.

	Punch time is always the server clock. A second IN without an OUT auto-closes the open IN.
	A completed IN+OUT pair for today cannot be repeated.
	"""
	employee = get_session_employee(("name", "employee_name", "company", "geofence_policy"))
	lat, lng = _parse_coordinates(latitude, longitude)
	log_type = _parse_punch_type(punch_type)

	# Serialise concurrent punches from the same employee (e.g. a double tap).
	frappe.db.get_value("Employee", employee.name, "name", for_update=True)

	day = today_punch_state(employee.name)
	if day["today_complete"]:
		raise ApiError("You have already punched in and out for today", 400)

	match = resolve_geofence(lat, lng, get_employee_geofences(employee.name))
	if match is None:
		raise ApiError("No work location is assigned to you yet. Please contact HR.", 400)

	if not match.is_within and get_geofence_policy(employee) == POLICY_REJECT:
		raise ApiError(
			"Outside allowed location",
			400,
			{
				"nearest_location": match.geofence.name,
				"distance_meters": round(match.distance_meters, 1),
				"radius_meters": match.geofence.radius_meters,
			},
		)

	now = now_datetime()
	last = get_last_checkin(employee.name)
	auto_closed = None

	if log_type == "OUT" and (not last or last.log_type != "IN"):
		raise ApiError("You are not punched in", 400)
	if log_type == "IN" and last and last.log_type == "IN":
		auto_closed = _auto_close(employee.name, last, device_id)

	checkin = frappe.get_doc(
		{
			"doctype": "Employee Checkin",
			"employee": employee.name,
			"log_type": log_type,
			"time": now,
			"device_id": _clean_device_id(device_id),
			"latitude": lat,
			"longitude": lng,
			"is_within_geofence": 1 if match.is_within else 0,
			"geofence_location": match.geofence.name,
			"distance_from_geofence": round(match.distance_meters, 1),
			"client_captured_at": _parse_client_time(captured_at),
		}
	).insert(ignore_permissions=True)

	message = "Punch recorded successfully"
	if not match.is_within:
		message = "Punch recorded outside the allowed location and flagged for HR review"

	return success(
		{
			"checkin": checkin.name,
			"punch_type": log_type,
			"time": checkin.time,
			"current_status": log_type,
			"is_within_geofence": bool(match.is_within),
			"geofence_location": match.geofence.name,
			"distance_meters": round(match.distance_meters, 1),
			"auto_closed_checkin": auto_closed,
		},
		message,
	)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_punch_status():
	"""Current IN/OUT state, today's punches/shift, and active geofences."""
	employee = get_session_employee(("name", "employee_name", "company", "geofence_policy"))
	last = get_last_checkin(employee.name)
	day = today_punch_state(employee.name)
	return {
		"employee": employee.name,
		"employee_name": employee.employee_name,
		"current_status": last.log_type if last else "OUT",
		"last_punch": _punch_dict(last) if last else None,
		"today_complete": day["today_complete"],
		"today_punches": day["today_punches"],
		"today_shift": day["today_shift"],
		"first_in": day["first_in"],
		"last_out": day["last_out"],
		"worked_hours": day["worked_hours"],
		"worked_minutes": day["worked_minutes"],
		"geofence_policy": get_geofence_policy(employee),
		"geofences": [
			{
				"name": g.name,
				"latitude": g.latitude,
				"longitude": g.longitude,
				"radius_meters": g.radius_meters,
			}
			for g in get_employee_geofences(employee.name)
		],
	}


@frappe.whitelist(methods=["GET", "POST"])
@api_endpoint
def get_live_attendance(date=None, company=None, department=None, employee=None):
	"""HR: one-day present / absent / late / on-leave snapshot (same rules as Attendance Summary)."""
	if not is_hr():
		raise ApiError("Only HR can view live attendance", 403)
	if date not in (None, "") and not _is_iso_date(date):
		raise ApiError("date must be YYYY-MM-DD", 400)
	return live_attendance(
		{
			"date": date or None,
			"company": company or None,
			"department": department or None,
			"employee": employee or None,
		}
	)


@frappe.whitelist(methods=["GET", "POST"])
@api_endpoint
def my_attendance(month=None):
	"""Logged-in employee: month of daily present / absent / late / leave with times and hours."""
	employee = get_session_employee(("name",))
	return employee_month_attendance(employee.name, month)


def get_employee_geofences(employee: str) -> list[Geofence]:
	location_names = frappe.get_all(
		"Employee Geofence Map", filters={"employee": employee}, pluck="geofence_location"
	)
	if not location_names:
		return []
	rows = frappe.get_all(
		"Geofence Location",
		filters={"name": ("in", location_names), "is_active": 1},
		fields=["name", "latitude", "longitude", "radius_meters"],
	)
	return [Geofence(r.name, flt(r.latitude), flt(r.longitude), flt(r.radius_meters)) for r in rows]


def get_geofence_policy(employee=None, company: str | None = None) -> str:
	"""Employee override, then Company, then HRMS Custom Settings. Default Reject.

	`employee` may be an Employee name or a row/dict with `geofence_policy` and `company`.
	"""
	if employee is not None and not isinstance(employee, str):
		emp_policy = employee.get("geofence_policy")
		company = company or employee.get("company")
		if emp_policy:
			return emp_policy
	elif employee:
		row = frappe.db.get_value("Employee", employee, ["geofence_policy", "company"], as_dict=True)
		if row:
			if row.geofence_policy:
				return row.geofence_policy
			company = company or row.company
	override = company and frappe.db.get_value("Company", company, "geofence_policy")
	return override or frappe.db.get_single_value("HRMS Custom Settings", "geofence_policy") or POLICY_REJECT


def get_last_checkin(employee: str):
	rows = frappe.get_all(
		"Employee Checkin",
		filters={"employee": employee},
		fields=["name", "log_type", "time", "geofence_location"],
		order_by="time desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def today_punch_state(employee: str, day=None) -> dict:
	"""Today's first IN / last real OUT, assigned shift, and whether the day is already closed."""
	requested = getdate(day) if day else getdate()
	day = _active_attendance_date(employee, requested)
	checkins = _load_checkins([employee], day, day).get(employee, [])
	by_day = {
		day + timedelta(days=offset): shift_for_day(employee, day + timedelta(days=offset)) for offset in (-1, 0, 1)
	}
	shift = by_day.get(day)
	real = [row for row in checkins if not cint(row.get("is_auto_closed"))]
	first_in, last_out = _pair_punches(real, day, shift, by_day)
	prev_shift = by_day.get(day - timedelta(days=1))
	next_shift = by_day.get(day + timedelta(days=1))
	visible = []
	for row in real:
		lo, hi = log_search_window(day, shift, row.log_type, prev_shift, next_shift)
		if lo <= get_datetime(row.time) <= hi:
			visible.append(row)
	visible.sort(key=lambda row: get_datetime(row.time))
	minutes = None
	if first_in and last_out:
		minutes = int((get_datetime(last_out.time) - get_datetime(first_in.time)).total_seconds() // 60)
		if minutes < 0:
			minutes = None
	return {
		"date": day.isoformat(),
		"today_complete": bool(first_in and last_out),
		"today_punches": [_punch_dict(row) for row in visible],
		"today_shift": _public_shift(shift) if shift else None,
		"first_in": _punch_dict(first_in) if first_in else None,
		"last_out": _punch_dict(last_out) if last_out else None,
		"worked_minutes": minutes,
		"worked_hours": f"{minutes // 60}h {minutes % 60}m" if minutes is not None else None,
	}


def _active_attendance_date(employee: str, day):
	"""Keep an open overnight shift on its start date until the next shift can accept an IN.

	After midnight the employee is still on yesterday's shift while that shift's punch-out
	window is open. Once `now` falls inside today's IN window, punches belong to today so a
	finished night shift does not block the next shift's punch-in.
	"""
	day = getdate(day)
	now = now_datetime()
	if getdate(now) != day:
		return day
	prev = day - timedelta(days=1)
	prev_shift = shift_for_day(employee, prev)
	if not prev_shift or not prev_shift.get("is_overnight"):
		return day
	_, end, _ = shift_window(prev, prev_shift)
	today_shift = shift_for_day(employee, day)
	if today_shift:
		next_shift = shift_for_day(employee, day + timedelta(days=1))
		in_lo, _in_hi = log_search_window(day, today_shift, "IN", prev_shift, next_shift)
		if now >= in_lo:
			return day
	if now <= end + timedelta(hours=4):
		return prev
	return day


def _punch_dict(row) -> dict:
	return {
		"checkin": row.name,
		"punch_type": row.log_type,
		"time": row.time,
		"geofence_location": row.geofence_location if row.get("geofence_location") else None,
	}


def _public_shift(shift: dict) -> dict:
	return {
		"name": shift.get("name"),
		"start_time": shift.get("start_time"),
		"end_time": shift.get("end_time"),
		"grace_minutes": int(shift.get("grace_minutes") or 0),
		"early_exit_grace_minutes": int(shift.get("early_exit_grace_minutes") or 0),
		"working_hours": flt(shift.get("working_hours") or 0),
		"minimum_hours_present": flt(shift.get("minimum_hours_present") or 0),
		"minimum_hours_half_day": flt(shift.get("minimum_hours_half_day") or 0),
		"allow_flexible_hours": int(shift.get("allow_flexible_hours") or 0),
		"color": shift.get("color") or "#1F5EFF",
		"location": shift.get("location"),
		"is_overnight": bool(shift.get("is_overnight")),
		"source": shift.get("source"),
	}


def _auto_close(employee: str, open_in, device_id) -> str:
	"""Close a dangling IN at the IN time itself (zero duration), so unverified time is never
	credited. HR reviews these via `is_auto_closed`."""
	doc = frappe.get_doc(
		{
			"doctype": "Employee Checkin",
			"employee": employee,
			"log_type": "OUT",
			"time": get_datetime(open_in.time),
			"device_id": _clean_device_id(device_id),
			"is_auto_closed": 1,
		}
	).insert(ignore_permissions=True)
	return doc.name


def _parse_coordinates(latitude, longitude) -> tuple[float, float]:
	if latitude in (None, "") or longitude in (None, ""):
		raise ApiError("Location is required to punch. Please enable location services.", 400)
	try:
		lat, lng = float(latitude), float(longitude)
		validate_coordinates(lat, lng)
	except (TypeError, ValueError) as e:
		raise ApiError(f"Invalid location: {e}", 400) from e
	return lat, lng


def _parse_punch_type(punch_type) -> str:
	value = (punch_type or "").strip().upper()
	if value not in PUNCH_TYPES:
		raise ApiError("punch_type must be IN or OUT", 400)
	return value


def _parse_client_time(value):
	if not value:
		return None
	try:
		return get_datetime(value).replace(tzinfo=None, microsecond=0)
	except Exception:
		return None


def _clean_device_id(device_id) -> str | None:
	return str(device_id)[:140] if device_id else None


def _is_iso_date(value) -> bool:
	try:
		datetime.strptime(str(value).strip()[:10], "%Y-%m-%d")
		return True
	except ValueError:
		return False
