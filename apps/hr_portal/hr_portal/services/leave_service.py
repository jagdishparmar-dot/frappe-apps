from __future__ import annotations

from datetime import date, timedelta

import frappe

ACTIVE_LEAVE_STATUSES = ("Pending", "Approved")


def day_count(from_date: str, to_date: str) -> int:
	start = date.fromisoformat(from_date)
	end = date.fromisoformat(to_date)
	if end < start:
		return 0
	return (end - start).days + 1


def dates_in_range(from_date: str, to_date: str) -> list[str]:
	dates: list[str] = []
	cursor = date.fromisoformat(from_date)
	end = date.fromisoformat(to_date)
	while cursor <= end:
		dates.append(cursor.isoformat())
		cursor += timedelta(days=1)
	return dates


def ranges_overlap(from_a: str, to_a: str, from_b: str, to_b: str) -> bool:
	return from_a <= to_b and from_b <= to_a


def _day_meta(date_iso: str, tz_name: str) -> tuple[str, str]:
	from hr_portal.lib.attendance_shift import date_iso_in_timezone

	ms = frappe.utils.get_datetime(f"{date_iso} 12:00:00").timestamp() * 1000
	_, day = date_iso_in_timezone(int(ms), tz_name)
	return day, date_iso


def ensure_leave_balance(
	employee: str,
	leave_type: str,
	year: int,
	opening: float = 0,
) -> frappe.Document:
	existing = frappe.db.get_value(
		"HR Leave Balance",
		{"employee": employee, "leave_type": leave_type, "year": year},
		"name",
	)
	if existing:
		return frappe.get_doc("HR Leave Balance", existing)
	doc = frappe.get_doc(
		{
			"doctype": "HR Leave Balance",
			"employee": employee,
			"leave_type": leave_type,
			"year": year,
			"balance": opening,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc


def find_overlapping_requests(
	employee: str,
	from_date: str,
	to_date: str,
	exclude: str | None = None,
) -> list[dict]:
	rows = frappe.get_all(
		"HR Leave Request",
		filters={"employee": employee, "status": ("in", list(ACTIVE_LEAVE_STATUSES))},
		fields=["name", "from_date", "to_date", "status"],
		limit=200,
	)
	overlaps = []
	for row in rows:
		if exclude and row.name == exclude:
			continue
		if ranges_overlap(str(row.from_date), str(row.to_date), from_date, to_date):
			overlaps.append(row)
	return overlaps


def validate_leave_application(
	employee: str,
	leave_type: str,
	from_date: str,
	to_date: str,
	exclude_request: str | None = None,
) -> dict:
	days = day_count(from_date, to_date)
	if days <= 0:
		return {"ok": False, "error": "Invalid date range."}

	overlaps = find_overlapping_requests(employee, from_date, to_date, exclude_request)
	if overlaps:
		first = overlaps[0]
		return {
			"ok": False,
			"error": f"Leave already {first.status.lower()} for {first.from_date} to {first.to_date}.",
		}

	year = int(from_date[:4])
	balance_doc = ensure_leave_balance(employee, leave_type, year)
	if float(balance_doc.balance or 0) < days:
		return {"ok": False, "error": "Insufficient leave balance."}

	return {"ok": True, "days": days, "balance": balance_doc}


def _leave_attendance_status(request_status: str) -> str | None:
	if request_status == "Pending":
		return "LEAVE_PENDING"
	if request_status == "Approved":
		return "ON_LEAVE"
	return None


def _upsert_leave_attendance_day(
	employee: str,
	user: str,
	date_iso: str,
	leave_request: str,
	leave_type_name: str,
	status: str,
	tz_name: str,
) -> None:
	existing = frappe.get_all(
		"HR Attendance",
		filters={"employee": employee, "date_iso": date_iso},
		pluck="name",
		limit=1,
	)
	day_of_week, _ = _day_meta(date_iso, tz_name)
	payload = {
		"employee": employee,
		"user": user,
		"date_iso": date_iso,
		"day_of_week": day_of_week,
		"status": status,
		"clock_in_time": "",
		"clock_out_time": "",
		"total_minutes": 0,
		"site": "",
		"geofence_status": "UNKNOWN",
		"distance_meters": 0,
		"note": f"Leave: {leave_type_name}",
		"location_name": "Leave",
		"leave_request": leave_request,
		"device_id": "",
	}

	if existing:
		doc = frappe.get_doc("HR Attendance", existing[0])
		if doc.clock_in_time:
			doc.note = f"{payload['note']} (punch also recorded)"
			doc.leave_request = leave_request
		else:
			doc.update(payload)
		doc.flags.ignore_permissions = True
		doc.save()
		return

	doc = frappe.get_doc({"doctype": "HR Attendance", **payload})
	doc.flags.ignore_permissions = True
	doc.insert()


def clear_leave_attendance_for_request(
	employee: str,
	leave_request: str,
	dates: list[str],
) -> None:
	for date_iso in dates:
		rows = frappe.get_all(
			"HR Attendance",
			filters={"employee": employee, "date_iso": date_iso, "leave_request": leave_request},
			pluck="name",
			limit=1,
		)
		if not rows:
			continue
		doc = frappe.get_doc("HR Attendance", rows[0])
		if doc.clock_in_time:
			doc.note = (doc.note or "").replace(f"Leave:", "").strip()
			doc.leave_request = ""
			doc.flags.ignore_permissions = True
			doc.save()
			continue
		frappe.delete_doc("HR Attendance", doc.name, force=1)


def sync_leave_request_to_attendance(request: frappe.Document, leave_type_name: str) -> None:
	settings = frappe.get_single("HR Settings")
	tz = settings.timezone or "Asia/Kolkata"
	dates = dates_in_range(str(request.from_date), str(request.to_date))
	attendance_status = _leave_attendance_status(request.status)

	if not attendance_status:
		clear_leave_attendance_for_request(request.employee, request.name, dates)
		return

	for date_iso in dates:
		_upsert_leave_attendance_day(
			request.employee,
			request.user or "",
			date_iso,
			request.name,
			leave_type_name,
			attendance_status,
			tz,
		)


def seed_leave_balances_for_employee(employee: str, year: int | None = None) -> None:
	year = year or frappe.utils.now_datetime().year
	types = frappe.get_all(
		"HR Leave Type",
		filters={"status": "Active"},
		fields=["name", "accrual_per_month", "max_balance"],
	)
	for row in types:
		opening = min(float(row.max_balance or 24), float(row.accrual_per_month or 1) * 12)
		ensure_leave_balance(employee, row.name, year, opening)
