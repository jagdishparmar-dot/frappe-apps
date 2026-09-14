from __future__ import annotations

import frappe

from hr_portal.constants import DIRECTORY_ROLES
from hr_portal.lib.attendance_shift import add_days_iso, date_iso_in_timezone
from hr_portal.permissions import is_staff
from hr_portal.services.punch_service import attendance_to_record


def _today_iso() -> str:
	settings = frappe.get_single("HR Settings")
	tz = settings.timezone or "Asia/Kolkata"
	today, _ = date_iso_in_timezone(int(frappe.utils.now_datetime().timestamp() * 1000), tz)
	return today


def _employee_lookup() -> dict[str, str]:
	rows = frappe.get_all("HR Employee", fields=["name", "employee_name"], limit=500)
	return {row.name: row.employee_name for row in rows}


def _leave_type_name(leave_type_id: str) -> str:
	if not leave_type_id:
		return "Leave"
	return (
		frappe.db.get_value("HR Leave Type", leave_type_id, "leave_type_name")
		or leave_type_id
	)


def _shift_label(shift_id: str | None) -> str:
	if not shift_id:
		return "—"
	row = frappe.db.get_value("HR Shift", shift_id, ["shift_name", "code"], as_dict=True)
	if not row:
		return shift_id
	return f"{row.shift_name} ({row.code})"


def build_dashboard_snapshot() -> dict:
	if not is_staff() and frappe.session.user != "Administrator":
		frappe.throw("Not permitted", frappe.PermissionError)

	today = _today_iso()
	yesterday = add_days_iso(today, -1)
	emp_lookup = _employee_lookup()

	active = frappe.db.count("HR Employee", {"status": "Active"})
	inactive = frappe.db.count("HR Employee", {"status": "Inactive"})
	invited = frappe.db.count("HR Employee", {"status": "Invited"})

	by_type: dict[str, int] = {}
	for row in frappe.get_all(
		"HR Employee",
		filters={"status": "Active"},
		fields=["employment_type"],
		limit=500,
	):
		key = (row.employment_type or "Other").strip() or "Other"
		by_type[key] = by_type.get(key, 0) + 1

	attendance_rows = frappe.get_all(
		"HR Attendance",
		filters={"date_iso": today},
		fields=["name"],
		limit=500,
	)
	rows = [attendance_to_record(frappe.get_doc("HR Attendance", row.name)) for row in attendance_rows]
	for row in rows:
		employee_id = frappe.db.get_value("HR Attendance", row["id"], "employee")
		row["employeeId"] = employee_id or ""
		row["employeeName"] = emp_lookup.get(employee_id, employee_id or "Employee")

	overnight_open = frappe.get_all(
		"HR Attendance",
		filters={
			"date_iso": yesterday,
			"clock_in_time": ("is", "set"),
			"clock_out_time": ("is", "not set"),
		},
		fields=["name"],
		limit=200,
	)
	open_overnight = []
	for row in overnight_open:
		rec = attendance_to_record(frappe.get_doc("HR Attendance", row.name))
		if rec.get("clockInTime") and not rec.get("clockOutTime"):
			employee_id = frappe.db.get_value("HR Attendance", rec["id"], "employee")
			rec["employeeId"] = employee_id or ""
			rec["employeeName"] = emp_lookup.get(employee_id, employee_id or "Employee")
			open_overnight.append(rec)

	present = sum(1 for r in rows if r.get("status") == "PRESENT")
	late = sum(1 for r in rows if r.get("status") == "LATE")
	absent = sum(1 for r in rows if r.get("status") == "ABSENT")
	on_leave = sum(1 for r in rows if r.get("status") in ("ON_LEAVE", "LEAVE_PENDING"))
	half_day = sum(1 for r in rows if r.get("status") == "HALF_DAY")
	marked = len({r.get("employeeId") for r in rows if r.get("employeeId")})
	open_today = [r for r in rows if r.get("clockInTime") and not r.get("clockOutTime")]
	open_shifts = len(open_today) + len(open_overnight)
	unmarked = max(active - marked, 0)

	pending_leave = frappe.get_all(
		"HR Leave Request",
		filters={"status": "pending"},
		fields=["name", "employee", "leave_type", "from_date", "to_date", "days", "status"],
		order_by="modified desc",
		limit=8,
	)
	pending_items = []
	for row in pending_leave:
		pending_items.append(
			{
				"id": row.name,
				"employeeName": emp_lookup.get(row.employee, row.employee),
				"leaveTypeName": _leave_type_name(row.leave_type),
				"fromDate": str(row.from_date),
				"toDate": str(row.to_date),
				"days": float(row.days or 0),
				"status": row.status,
			}
		)

	approved_leave = frappe.get_all(
		"HR Leave Request",
		filters={"status": "approved", "from_date": ("<=", today)},
		fields=["name", "employee", "leave_type", "from_date", "to_date", "days", "status"],
		order_by="modified desc",
		limit=200,
	)
	on_leave_today_items = []
	for row in approved_leave:
		if str(row.to_date) < today:
			continue
		on_leave_today_items.append(
			{
				"id": row.name,
				"employeeName": emp_lookup.get(row.employee, row.employee),
				"leaveTypeName": _leave_type_name(row.leave_type),
				"fromDate": str(row.from_date),
				"toDate": str(row.to_date),
				"days": float(row.days or 0),
				"status": row.status,
			}
		)
		if len(on_leave_today_items) >= 8:
			break

	pending_regs = frappe.get_all(
		"HR Regularization",
		filters={"status": "pending"},
		fields=[
			"name",
			"employee",
			"date_iso",
			"requested_clock_in",
			"requested_clock_out",
			"requested_out_date_iso",
			"reason",
		],
		order_by="modified desc",
		limit=6,
	)
	regularization_items = [
		{
			"id": row.name,
			"employeeName": emp_lookup.get(row.employee, row.employee),
			"dateIso": str(row.date_iso),
			"requestedClockIn": row.requested_clock_in or "",
			"requestedClockOut": row.requested_clock_out or "",
			"requestedOutDateIso": str(row.requested_out_date_iso or row.date_iso),
			"reason": row.reason or "",
		}
		for row in pending_regs
	]

	pending_shift_changes = frappe.get_all(
		"HR Shift Change Request",
		filters={"status": "pending"},
		fields=["name", "employee", "date_iso", "sequence", "current_shift", "requested_shift", "reason"],
		order_by="modified desc",
		limit=6,
	)
	shift_change_items = [
		{
			"id": row.name,
			"employeeName": emp_lookup.get(row.employee, row.employee),
			"dateIso": str(row.date_iso),
			"sequence": int(row.sequence or 1),
			"currentShiftLabel": _shift_label(row.current_shift),
			"requestedShiftLabel": _shift_label(row.requested_shift),
			"reason": row.reason or "",
		}
		for row in pending_shift_changes
	]

	on_duty_now = sorted(
		[
			{
				"employeeId": r.get("employeeId"),
				"employeeName": r.get("employeeName") or "Employee",
				"clockInTime": r.get("clockInTime") or "",
				"siteName": r.get("locationName") or "—",
				"status": r.get("status") or "",
				"geofenceStatus": frappe.db.get_value("HR Attendance", r.get("id"), "geofence_status") or "",
			}
			for r in [*open_today, *open_overnight]
		],
		key=lambda item: item.get("clockInTime") or "",
		reverse=True,
	)[:10]

	recent_docs = frappe.get_all(
		"HR Attendance",
		fields=["name", "employee", "clock_in_timestamp"],
		order_by="clock_in_timestamp desc",
		limit=12,
	)
	recent = []
	for row in recent_docs:
		rec = attendance_to_record(frappe.get_doc("HR Attendance", row.name))
		rec["employeeId"] = row.employee
		rec["employeeName"] = emp_lookup.get(row.employee, row.employee)
		recent.append(rec)

	is_admin = bool(set(frappe.get_roles()).intersection(set(DIRECTORY_ROLES))) or frappe.session.user == "Administrator"

	return {
		"today": today,
		"employees": {
			"active": active,
			"inactive": inactive,
			"invited": invited,
			"byType": by_type,
		},
		"attendance": {
			"present": present,
			"late": late,
			"absent": absent,
			"onLeave": on_leave,
			"halfDay": half_day,
			"openShifts": open_shifts,
			"marked": marked,
			"unmarked": unmarked,
		},
		"leave": {
			"pending": len(pending_items),
			"onLeaveToday": len(on_leave_today_items),
			"pendingItems": pending_items,
			"onLeaveTodayItems": on_leave_today_items,
		},
		"regularizationsPending": len(regularization_items),
		"adminQueues": {
			"regularizationsPending": len(regularization_items),
			"regularizationItems": regularization_items,
			"shiftChangesPending": len(shift_change_items),
			"shiftChangeItems": shift_change_items,
		}
		if is_admin
		else None,
		"onDutyNow": on_duty_now,
		"recent": recent,
	}
