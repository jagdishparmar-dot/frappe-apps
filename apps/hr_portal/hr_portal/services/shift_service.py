from __future__ import annotations

import csv
import io
from datetime import date, timedelta

import frappe

from hr_portal.lib.attendance_shift import (
	add_days_iso,
	candidate_shift_dates,
	date_iso_in_timezone,
	format_shift_window_label,
	shift_from_employee_fallback,
)
from hr_portal.services.punch_service import OPEN_SHIFT_MAX_AGE_MS, _hhmm, _ms_from_dt


def _settings() -> dict:
	row = frappe.get_single("HR Settings")
	return {
		"timezone": row.timezone or "Asia/Kolkata",
		"late_grace_minutes": int(row.late_grace_minutes or 15),
	}


def _shift_doc(name: str | None) -> dict | None:
	if not name:
		return None
	row = frappe.db.get_value(
		"HR Shift",
		name,
		[
			"name",
			"shift_name",
			"code",
			"shift_type",
			"start_time",
			"end_time",
			"status",
		],
		as_dict=True,
	)
	if not row or row.status != "Active":
		return None
	return {
		"id": row.name,
		"name": row.shift_name,
		"code": row.code,
		"shiftType": row.shift_type or "general",
		"startTime": _hhmm(row.start_time),
		"endTime": _hhmm(row.end_time),
	}


def _employee_fallback(employee_name: str) -> dict:
	emp = frappe.db.get_value(
		"HR Employee",
		employee_name,
		["default_shift", "work_shift_start", "work_shift_end"],
		as_dict=True,
	) or {}
	settings = _settings()
	shift = _shift_doc(emp.default_shift)
	if shift:
		return shift
	fb = shift_from_employee_fallback(
		_hhmm(emp.work_shift_start) or "09:00",
		_hhmm(emp.work_shift_end) or "18:00",
		settings["late_grace_minutes"],
	)
	return {
		"id": fb.id,
		"name": fb.name,
		"code": fb.code,
		"shiftType": fb.shift_type,
		"startTime": fb.start_time,
		"endTime": fb.end_time,
	}


def get_employee_today_shifts(employee_name: str) -> dict:
	settings = _settings()
	tz = settings["timezone"]
	now_ms = int(frappe.utils.now_datetime().timestamp() * 1000)
	today_iso, _ = date_iso_in_timezone(now_ms, tz)
	candidate_dates = candidate_shift_dates(now_ms, tz)

	assignments = frappe.get_all(
		"HR Shift Assignment",
		filters={
			"employee": employee_name,
			"assignment_date": ("in", candidate_dates),
			"status": "Scheduled",
		},
		fields=["name", "shift", "assignment_date", "sequence", "note"],
		order_by="sequence asc",
		limit=20,
	)
	roster_today = [a for a in assignments if str(a.assignment_date) == today_iso]
	shifts: list[dict] = []

	if roster_today:
		for row in roster_today:
			shift = _shift_doc(row.shift) or _employee_fallback(employee_name)
			shifts.append(
				{
					"assignmentId": row.name,
					"dateIso": str(row.assignment_date),
					"sequence": int(row.sequence or 1),
					"shiftId": shift["id"],
					"name": shift["name"],
					"code": shift["code"],
					"shiftType": shift["shiftType"],
					"startTime": shift["startTime"],
					"endTime": shift["endTime"],
					"windowLabel": format_shift_window_label(
						{
							"startTime": shift["startTime"],
							"endTime": shift["endTime"],
							"crossesMidnight": shift["startTime"] > shift["endTime"],
						}
					),
					"source": "roster",
					"note": row.note or None,
				}
			)
	else:
		shift = _employee_fallback(employee_name)
		shifts.append(
			{
				"dateIso": today_iso,
				"sequence": 1,
				"shiftId": shift["id"],
				"name": shift["name"],
				"code": shift["code"],
				"shiftType": shift["shiftType"],
				"startTime": shift["startTime"],
				"endTime": shift["endTime"],
				"windowLabel": format_shift_window_label(
					{
						"startTime": shift["startTime"],
						"endTime": shift["endTime"],
						"crossesMidnight": shift["startTime"] > shift["endTime"],
					}
				),
				"source": "default",
			}
		)

	return {"dateIso": today_iso, "timezone": tz, "shifts": shifts}


def list_shift_catalog() -> list[dict]:
	rows = frappe.get_all(
		"HR Shift",
		filters={"status": "Active"},
		fields=["name", "shift_name", "code", "shift_type", "start_time", "end_time"],
		order_by="shift_name asc",
		limit=100,
	)
	return [
		{
			"id": row.name,
			"name": row.shift_name,
			"code": row.code,
			"shiftType": row.shift_type or "general",
			"startTime": _hhmm(row.start_time),
			"endTime": _hhmm(row.end_time),
		}
		for row in rows
	]


def list_roster(from_date: str, to_date: str, employee: str = "") -> list[dict]:
	filters: dict = {
		"assignment_date": ("between", [from_date, to_date]),
	}
	if employee:
		filters["employee"] = employee
	rows = frappe.get_all(
		"HR Shift Assignment",
		filters=filters,
		fields=["name", "employee", "assignment_date", "shift", "sequence", "site", "status", "note"],
		order_by="assignment_date asc, sequence asc",
		limit=5000,
	)
	result = []
	for row in rows:
		emp = frappe.db.get_value("HR Employee", row.employee, ["employee_name", "employee_code"], as_dict=True) or {}
		shift = _shift_doc(row.shift) or {}
		result.append(
			{
				"id": row.name,
				"employeeId": row.employee,
				"employeeName": emp.get("employee_name") or row.employee,
				"employeeCode": emp.get("employee_code") or "",
				"dateIso": str(row.assignment_date),
				"shiftId": row.shift,
				"shiftName": shift.get("name") or row.shift,
				"shiftCode": shift.get("code") or "",
				"sequence": int(row.sequence or 1),
				"siteId": row.site or "",
				"status": (row.status or "Scheduled").lower(),
				"note": row.note or "",
			}
		)
	return result


def save_assignment(
	employee: str,
	assignment_date: str,
	shift: str,
	sequence: int = 1,
	site: str = "",
	note: str = "",
	name: str | None = None,
) -> str:
	payload = {
		"employee": employee,
		"assignment_date": assignment_date,
		"shift": shift,
		"sequence": int(sequence or 1),
		"site": site or "",
		"status": "Scheduled",
		"note": note or "",
	}
	if name:
		doc = frappe.get_doc("HR Shift Assignment", name)
		doc.update(payload)
		doc.flags.ignore_permissions = True
		doc.save()
		return doc.name
	doc = frappe.get_doc({"doctype": "HR Shift Assignment", **payload})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def delete_assignment(name: str) -> None:
	frappe.delete_doc("HR Shift Assignment", name, force=1)


def generate_rotational_roster(
	employee: str,
	start_date: str,
	days: int,
	pattern: str,
) -> int:
	tokens = [part.strip() for part in pattern.split(",") if part.strip()]
	if not tokens:
		frappe.throw("Pattern must include at least one shift code or OFF.")
	created = 0
	for i in range(days):
		date_iso = add_days_iso(start_date, i)
		token = tokens[i % len(tokens)]
		if token.upper() == "OFF":
			continue
		shift_name = frappe.db.get_value("HR Shift", {"code": token.upper(), "status": "Active"}, "name")
		if not shift_name:
			frappe.throw(f"Unknown shift in pattern: {token}")
		save_assignment(employee, date_iso, shift_name)
		created += 1
	return created


def import_roster_csv(csv_text: str) -> dict:
	reader = csv.DictReader(io.StringIO(csv_text))
	if not reader.fieldnames:
		return {"ok": False, "error": "CSV is empty."}

	header_map = {
		"employee_code": "employee_code",
		"employeecode": "employee_code",
		"employee": "employee_code",
		"shift_code": "shift_code",
		"shiftcode": "shift_code",
		"shift": "shift_code",
		"date": "date",
		"date_iso": "date",
		"sequence": "sequence",
		"note": "note",
	}
	normalized_headers = {}
	for h in reader.fieldnames:
		key = header_map.get((h or "").strip().lower().replace(" ", "_"))
		if key:
			normalized_headers[h] = key

	created = 0
	errors: list[str] = []
	for line_no, raw in enumerate(reader, start=2):
		row = {(normalized_headers.get(k, k)): (v or "").strip() for k, v in raw.items()}
		code = row.get("employee_code", "").upper()
		shift_code = row.get("shift_code", "").upper()
		date_iso = row.get("date", "")
		if not code or not date_iso:
			errors.append(f"Row {line_no}: employee code and date are required.")
			continue
		employee = frappe.db.get_value("HR Employee", {"employee_code": code}, "name")
		if not employee:
			errors.append(f'Row {line_no}: Unknown employee code "{code}".')
			continue
		if shift_code == "OFF":
			existing = frappe.get_all(
				"HR Shift Assignment",
				filters={"employee": employee, "assignment_date": date_iso},
				pluck="name",
			)
			for name in existing:
				delete_assignment(name)
			continue
		shift = frappe.db.get_value("HR Shift", {"code": shift_code, "status": "Active"}, "name")
		if not shift:
			errors.append(f'Row {line_no}: Unknown shift code "{shift_code}".')
			continue
		seq = int(row.get("sequence") or 1)
		save_assignment(employee, date_iso, shift, sequence=seq, note=row.get("note", ""))
		created += 1

	return {"ok": True, "created": created, "errors": errors}


def submit_shift_change_request(
	employee: str,
	user: str,
	date_iso: str,
	requested_shift: str,
	reason: str,
	sequence: int = 1,
) -> None:
	settings = _settings()
	today_iso, _ = date_iso_in_timezone(int(frappe.utils.now_datetime().timestamp() * 1000), settings["timezone"])
	if date_iso < today_iso:
		frappe.throw("Shift change can only be requested for today or future dates.")
	if not frappe.db.exists("HR Shift", {"name": requested_shift, "status": "Active"}):
		frappe.throw("Select a valid active shift.")

	existing = frappe.get_all(
		"HR Shift Assignment",
		filters={
			"employee": employee,
			"assignment_date": date_iso,
			"sequence": sequence,
			"status": "Scheduled",
		},
		fields=["name", "shift"],
		limit=1,
	)
	current_shift = existing[0].shift if existing else frappe.db.get_value("HR Employee", employee, "default_shift") or ""
	if current_shift == requested_shift:
		frappe.throw("Requested shift matches your current assignment.")

	pending = frappe.db.exists(
		"HR Shift Change Request",
		{"employee": employee, "date_iso": date_iso, "sequence": sequence, "status": "Pending"},
	)
	if pending:
		frappe.throw("A pending shift change request already exists for this date.")

	doc = frappe.get_doc(
		{
			"doctype": "HR Shift Change Request",
			"employee": employee,
			"user": user,
			"date_iso": date_iso,
			"sequence": sequence,
			"current_shift": current_shift or "",
			"current_assignment": existing[0].name if existing else "",
			"requested_shift": requested_shift,
			"reason": reason.strip(),
			"status": "Pending",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()


def review_shift_change_request(
	request_id: str,
	decision: str,
	review_note: str = "",
) -> None:
	doc = frappe.get_doc("HR Shift Change Request", request_id)
	if doc.status != "Pending":
		frappe.throw("This request was already reviewed.")

	if decision == "approved":
		employee = doc.employee
		site = frappe.db.get_value("HR Employee", employee, "primary_site") or ""
		payload = {
			"employee": employee,
			"assignment_date": doc.date_iso,
			"shift": doc.requested_shift,
			"sequence": doc.sequence,
			"site": site,
			"status": "Scheduled",
			"note": "Updated via approved shift change request",
		}
		if doc.current_assignment and frappe.db.exists("HR Shift Assignment", doc.current_assignment):
			assign = frappe.get_doc("HR Shift Assignment", doc.current_assignment)
			assign.update(payload)
			assign.flags.ignore_permissions = True
			assign.save()
		else:
			existing = frappe.get_all(
				"HR Shift Assignment",
				filters={
					"employee": employee,
					"assignment_date": doc.date_iso,
					"sequence": doc.sequence,
				},
				pluck="name",
				limit=1,
			)
			if existing:
				assign = frappe.get_doc("HR Shift Assignment", existing[0])
				assign.update(payload)
				assign.flags.ignore_permissions = True
				assign.save()
			else:
				save_assignment(
					employee,
					str(doc.date_iso),
					doc.requested_shift,
					sequence=int(doc.sequence or 1),
					site=site,
					note=payload["note"],
				)

	doc.status = "Approved" if decision == "approved" else "Rejected"
	doc.review_note = review_note
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = frappe.utils.now_datetime()
	doc.flags.ignore_permissions = True
	doc.save()


def get_live_presence() -> dict:
	cutoff_ms = int(frappe.utils.now_datetime().timestamp() * 1000) - OPEN_SHIFT_MAX_AGE_MS
	rows = frappe.get_all(
		"HR Attendance",
		filters={"clock_in_time": ("is", "set"), "clock_out_time": ("is", "not set")},
		fields=[
			"name",
			"employee",
			"site",
			"clock_in_time",
			"clock_in_timestamp",
			"geofence_status",
			"punch_in_lat",
			"punch_in_long",
			"location_name",
			"status",
		],
		order_by="clock_in_timestamp desc",
		limit=200,
	)
	checked_in = []
	by_site: dict[str, int] = {}
	field_count = 0
	for row in rows:
		if _ms_from_dt(row.clock_in_timestamp) < cutoff_ms:
			continue
		emp = frappe.db.get_value(
			"HR Employee", row.employee, ["employee_name", "employee_code"], as_dict=True
		) or {}
		site_name = ""
		if row.site:
			site_name = frappe.db.get_value("HR Site", row.site, "site_name") or row.site
		entry = {
			"attendanceId": row.name,
			"employeeId": row.employee,
			"employeeName": emp.get("employee_name") or row.employee,
			"employeeCode": emp.get("employee_code") or "",
			"siteId": row.site or "",
			"siteName": site_name or row.location_name or "Unassigned",
			"clockInTime": row.clock_in_time or "",
			"clockInTimestamp": _ms_from_dt(row.clock_in_timestamp),
			"geofenceStatus": row.geofence_status or "UNKNOWN",
			"punchInLat": row.punch_in_lat,
			"punchInLong": row.punch_in_long,
			"locationName": row.location_name or "",
			"status": row.status or "",
		}
		checked_in.append(entry)
		if row.site:
			by_site[row.site] = by_site.get(row.site, 0) + 1
		else:
			field_count += 1

	return {
		"checkedIn": checked_in,
		"bySiteId": by_site,
		"fieldCount": field_count,
		"totalCheckedIn": len(checked_in),
		"fetchedAt": frappe.utils.now_datetime().isoformat(),
	}
