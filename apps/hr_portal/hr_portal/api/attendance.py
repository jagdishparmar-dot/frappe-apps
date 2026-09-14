from __future__ import annotations

import csv
import io

import frappe
from frappe import _

from hr_portal.api.serialize import staff_or_own
from hr_portal.lib.attendance_shift import (
	finalize_attendance_on_punch_out,
	resolve_punch_out_occurrence,
	zoned_datetime_to_utc_ms,
)
from hr_portal.permissions import get_employee_name, is_staff
from hr_portal.services.punch_service import (
	_dt_from_ms,
	_get_settings,
	_hhmm,
	_load_default_shift,
	_ms_from_dt,
	_shift_from_doc,
	attendance_to_record,
	close_open_segments_for_regularization,
)
from hr_portal.utils import require_login, require_roles
from hr_portal.constants import DIRECTORY_ROLES, EMPLOYEE_WRITE_ROLES


def _own_or_staff_employee(employee_name: str | None = None) -> str:
	require_login()
	if employee_name:
		staff_or_own(employee_name)
		return employee_name
	name = get_employee_name()
	if not name:
		frappe.throw(_("No employee record found"))
	return name


@frappe.whitelist()
def list_history(employee: str = "", limit: int = 90) -> dict:
	employee_name = _own_or_staff_employee(employee or None)
	limit = min(max(int(limit or 90), 1), 365)
	rows = frappe.get_all(
		"HR Attendance",
		filters={"employee": employee_name},
		fields=["name"],
		order_by="date_iso desc, modified desc",
		limit=limit,
	)
	records = [attendance_to_record(frappe.get_doc("HR Attendance", row.name)) for row in rows]
	return {"ok": True, "records": records}


@frappe.whitelist()
def list_regularizations(employee: str = "") -> dict:
	employee_name = _own_or_staff_employee(employee or None)
	filters: dict = {"employee": employee_name}
	if is_staff():
		filters = {}
	rows = frappe.get_all(
		"HR Regularization",
		filters=filters,
		fields=[
			"name",
			"employee",
			"user",
			"date_iso",
			"reason",
			"requested_clock_in",
			"requested_clock_out",
			"requested_out_date_iso",
			"status",
			"review_note",
			"reviewed_by",
			"reviewed_at",
			"creation",
		],
		order_by="modified desc",
		limit=200,
	)
	requests = []
	for row in rows:
		emp_name = frappe.db.get_value("HR Employee", row.employee, "employee_name") or row.employee
		requests.append(
			{
				"id": row.name,
				"employeeId": row.employee,
				"employeeName": emp_name,
				"userId": row.user or "",
				"dateIso": str(row.date_iso),
				"reason": row.reason or "",
				"requestedClockIn": row.requested_clock_in or "",
				"requestedClockOut": row.requested_clock_out or "",
				"requestedOutDateIso": str(row.requested_out_date_iso or ""),
				"status": (row.status or "Pending").lower(),
				"reviewNote": row.review_note or "",
				"reviewedAt": str(row.reviewed_at or ""),
				"createdAt": str(row.creation or ""),
			}
		)
	return {"ok": True, "requests": requests}


@frappe.whitelist()
def submit_regularization(
	date_iso: str,
	reason: str,
	requested_clock_in: str = "",
	requested_clock_out: str = "",
	requested_out_date_iso: str = "",
) -> dict:
	employee_name = _own_or_staff_employee()
	if not date_iso or not reason or not str(reason).strip():
		frappe.throw(_("Date and reason are required"))
	user = frappe.session.user
	doc = frappe.get_doc(
		{
			"doctype": "HR Regularization",
			"employee": employee_name,
			"user": user,
			"date_iso": date_iso,
			"reason": reason.strip(),
			"requested_clock_in": requested_clock_in or "",
			"requested_clock_out": requested_clock_out or "",
			"requested_out_date_iso": requested_out_date_iso or "",
			"status": "Pending",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return {"ok": True}


@frappe.whitelist()
def review_regularization(
	regularization_id: str,
	decision: str,
	review_note: str = "",
) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	decision_norm = (decision or "").strip().lower()
	if decision_norm not in ("approved", "rejected"):
		frappe.throw(_("Invalid decision"))
	doc = frappe.get_doc("HR Regularization", regularization_id)
	if doc.status != "Pending":
		frappe.throw(_("Request already reviewed"))

	doc.status = "Approved" if decision_norm == "approved" else "Rejected"
	doc.review_note = (review_note or "").strip()
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = frappe.utils.now_datetime()

	if decision_norm == "approved":
		_apply_regularization(doc)

	doc.flags.ignore_permissions = True
	doc.save()
	return {"ok": True}


def _apply_regularization(reg: frappe.Document) -> None:
	settings = _get_settings()
	tz = settings["timezone"]
	late_grace = settings["late_grace_minutes"]
	employee = frappe.db.get_value(
		"HR Employee",
		reg.employee,
		["name", "user", "default_shift", "work_shift_start", "work_shift_end"],
		as_dict=True,
	)
	if not employee:
		frappe.throw(_("Employee not found"))

	existing = frappe.get_all(
		"HR Attendance",
		filters={"employee": reg.employee, "date_iso": reg.date_iso},
		pluck="name",
		limit=1,
	)
	out_date = str(reg.requested_out_date_iso or reg.date_iso)
	is_overnight = bool(reg.requested_clock_out and out_date != str(reg.date_iso))

	clock_in_ms = (
		zoned_datetime_to_utc_ms(str(reg.date_iso), reg.requested_clock_in, tz)
		if reg.requested_clock_in
		else None
	)
	clock_out_ms = (
		zoned_datetime_to_utc_ms(out_date, reg.requested_clock_out, tz)
		if reg.requested_clock_out
		else None
	)

	if existing:
		att = frappe.get_doc("HR Attendance", existing[0])
	else:
		att = frappe.new_doc("HR Attendance")
		att.employee = reg.employee
		att.user = employee.user or reg.user
		att.date_iso = reg.date_iso

	att.status = "PRESENT"
	att.note = f"Regularized: {reg.reason}"
	att.geofence_status = "UNKNOWN"
	att.distance_meters = 0
	att.location_name = "Regularization"
	att.site = ""
	att.device_id = ""
	att.is_overnight = is_overnight
	att.early_departure = False
	att.overtime_minutes = 0

	if reg.requested_clock_in:
		att.clock_in_time = reg.requested_clock_in
		att.clock_in_timestamp = _dt_from_ms(clock_in_ms)
	if reg.requested_clock_out:
		att.clock_out_time = reg.requested_clock_out
		att.clock_out_timestamp = _dt_from_ms(clock_out_ms)
		if clock_in_ms and clock_out_ms:
			att.total_minutes = max(0, round((clock_out_ms - clock_in_ms) / 60_000))

	shift = _shift_from_doc(employee.default_shift, late_grace) or _load_default_shift(employee, late_grace)
	if shift and clock_in_ms and clock_out_ms:
		occurrence = resolve_punch_out_occurrence(shift, str(reg.date_iso), tz)
		finalized = finalize_attendance_on_punch_out("PRESENT", clock_in_ms, clock_out_ms, occurrence)
		att.status = finalized.status
		att.early_departure = finalized.early_departure
		att.overtime_minutes = finalized.overtime_minutes
		att.total_minutes = finalized.total_minutes
		att.scheduled_start_timestamp = _dt_from_ms(occurrence.scheduled_start_ms)
		att.scheduled_end_timestamp = _dt_from_ms(occurrence.scheduled_end_ms)
		att.shift = shift.id
		att.is_overnight = occurrence.is_overnight or is_overnight

	att.flags.ignore_permissions = True
	att.save()
	reg.attendance = att.name

	if clock_out_ms:
		close_open_segments_for_regularization(
			att.name,
			clock_out_time=reg.requested_clock_out or "",
			clock_out_timestamp_ms=clock_out_ms,
		)


@frappe.whitelist()
def export_register(month: str = "") -> dict:
	require_roles(*DIRECTORY_ROLES)
	if not month:
		month = frappe.utils.today()[:7]
	start = f"{month}-01"
	end = frappe.utils.get_last_day(start)
	rows = frappe.get_all(
		"HR Attendance",
		filters={"date_iso": ("between", [start, end])},
		fields=[
			"name",
			"employee",
			"date_iso",
			"status",
			"clock_in_time",
			"clock_out_time",
			"total_minutes",
			"location_name",
		],
		order_by="date_iso asc",
		limit=5000,
	)
	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(
		["Employee", "Code", "Date", "Status", "In", "Out", "Minutes", "Location"]
	)
	for row in rows:
		emp = frappe.db.get_value(
			"HR Employee", row.employee, ["employee_name", "employee_code"], as_dict=True
		) or {}
		writer.writerow(
			[
				emp.get("employee_name") or row.employee,
				emp.get("employee_code") or "",
				row.date_iso,
				row.status,
				row.clock_in_time or "",
				row.clock_out_time or "",
				row.total_minutes or 0,
				row.location_name or "",
			]
		)
	return {"ok": True, "csv": buffer.getvalue(), "filename": f"attendance-{month}.csv"}
