"""Validate regularization times and write the matching Employee Checkin rows."""

from datetime import date, datetime, timedelta

import frappe
from frappe.utils import get_time, getdate

REVIEWED_STATUSES = ("Approved", "Rejected")


def format_time(value) -> str | None:
	if value in (None, ""):
		return None
	t = get_time(value)
	seconds = int(t.total_seconds()) if hasattr(t, "total_seconds") else t.hour * 3600 + t.minute * 60 + getattr(t, "second", 0)
	hours, rem = divmod(seconds, 3600)
	minutes, secs = divmod(rem, 60)
	return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def combine_date_time(day, time_value) -> datetime:
	d = getdate(day)
	t = get_time(time_value)
	seconds = int(t.total_seconds()) if hasattr(t, "total_seconds") else t.hour * 3600 + t.minute * 60 + getattr(t, "second", 0)
	hours, rem = divmod(seconds, 3600)
	minutes, secs = divmod(rem, 60)
	return datetime(d.year, d.month, d.day, hours, minutes, secs)


def resolve_out_day(day: date, check_in, check_out) -> date:
	if check_in in (None, "") or check_out in (None, ""):
		return day
	if get_time(check_out) < get_time(check_in):
		return day + timedelta(days=1)
	return day


def validate_request(employee: str, day, check_in, check_out, reason, exclude: str | None = None):
	if not employee or not day:
		frappe.throw("Employee and date are required")
	if not (reason or "").strip():
		frappe.throw("Please add a reason for this regularization")
	if check_in in (None, "") and check_out in (None, ""):
		frappe.throw("Request a check-in time, a check-out time, or both")
	target = getdate(day)
	if target > getdate():
		frappe.throw("You cannot regularize a future date")
	if not frappe.db.exists("Employee", employee):
		frappe.throw("Unknown employee")
	if frappe.db.get_value("Employee", employee, "status") != "Active":
		frappe.throw("Only an active employee can request regularization")
	open_name = frappe.db.get_value(
		"Attendance Regularization",
		{"employee": employee, "date": target, "status": "Open", "name": ("!=", exclude or "")},
		"name",
	)
	if open_name:
		frappe.throw(f"An open regularization already exists for this date ({open_name})")
	return {
		"date": target,
		"requested_check_in": format_time(check_in),
		"requested_check_out": format_time(check_out),
		"reason": (reason or "").strip(),
	}


def load_regularization(name: str):
	if not name or not frappe.db.exists("Attendance Regularization", name):
		frappe.throw("Regularization not found", frappe.DoesNotExistError)
	doc = frappe.new_doc("Attendance Regularization")
	doc.name = name
	doc.load_from_db()
	doc.set("__islocal", 0)
	return doc


def regularization_dict(doc) -> dict:
	return {
		"name": doc.name,
		"employee": doc.employee,
		"employee_name": doc.employee_name,
		"date": str(getdate(doc.date)),
		"requested_check_in": format_time(doc.requested_check_in),
		"requested_check_out": format_time(doc.requested_check_out),
		"reason": doc.reason,
		"status": doc.status,
		"remarks": doc.remarks,
		"reviewed_by": doc.reviewed_by,
		"reviewed_on": str(doc.reviewed_on) if doc.reviewed_on else None,
		"applied_in": doc.applied_in,
		"applied_out": doc.applied_out,
	}


def _existing_checkin(employee: str, log_type: str, day: date):
	start = datetime.combine(day, datetime.min.time())
	end = start + timedelta(days=1)
	order = "time asc, creation asc" if log_type == "IN" else "time desc, creation desc"
	rows = frappe.db.sql(
		f"""
		select name from `tabEmployee Checkin`
		where employee = %s and log_type = %s
			and time >= %s and time < %s
		order by {order}
		limit 1
		""",
		(employee, log_type, start, end),
	)
	return rows[0][0] if rows else None


def upsert_checkin(employee: str, log_type: str, when: datetime, regularization: str) -> str:
	day = when.date()
	existing = _existing_checkin(employee, log_type, day)
	if existing:
		doc = frappe.get_doc("Employee Checkin", existing)
		doc.time = when
		doc.attendance_regularization = regularization
		doc.device_id = doc.device_id or "regularization"
		doc.save(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc(
		{
			"doctype": "Employee Checkin",
			"employee": employee,
			"log_type": log_type,
			"time": when,
			"device_id": "regularization",
			"is_within_geofence": 1,
			"attendance_regularization": regularization,
		}
	).insert(ignore_permissions=True)
	return doc.name


def apply_regularization(doc) -> dict[str, str | None]:
	day = getdate(doc.date)
	applied = {"in": None, "out": None}
	if doc.requested_check_in:
		applied["in"] = upsert_checkin(
			doc.employee, "IN", combine_date_time(day, doc.requested_check_in), doc.name
		)
	if doc.requested_check_out:
		out_day = resolve_out_day(day, doc.requested_check_in, doc.requested_check_out)
		applied["out"] = upsert_checkin(
			doc.employee, "OUT", combine_date_time(out_day, doc.requested_check_out), doc.name
		)
	return applied
