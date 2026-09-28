"""Count leave days, balances, and overlapping applications."""

from datetime import date, timedelta

import frappe
from frappe.utils import cint, flt, getdate

from hrms_custom.utils.shifts import holidays_between

ACTIVE_APPLICATION_STATUSES = ("Open", "Approved")
REVIEWED_STATUSES = ("Approved", "Rejected")


def parse_year(year) -> int:
	if year in (None, ""):
		return getdate().year
	try:
		value = int(year)
		if 2000 <= value <= 2100:
			return value
	except (TypeError, ValueError):
		pass
	frappe.throw("year must be YYYY")


def year_bounds(year: int) -> tuple[date, date]:
	return date(year, 1, 1), date(year, 12, 31)


def company_holiday_dates(company: str | None, start: date, end: date) -> set[date]:
	if not company:
		return set()
	list_name = frappe.db.get_value("Company", company, "holiday_list")
	if not list_name:
		return set()
	return set(holidays_between([list_name], start, end))


def count_leave_days(
	from_date,
	to_date,
	*,
	half_day=0,
	half_day_date=None,
	include_holiday=0,
	holidays: set[date] | None = None,
) -> float:
	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		frappe.throw("To date cannot be before from date")
	half = cint(half_day)
	half_on = getdate(half_day_date) if half and half_day_date else (start if half and start == end else None)
	if half and not half_on:
		frappe.throw("Half-day date is required when the leave spans more than one day")
	if half_on and not (start <= half_on <= end):
		frappe.throw("Half-day date must fall within the leave period")

	skip_holidays = not cint(include_holiday)
	holiday_set = holidays or set()
	total = 0.0
	cursor = start
	while cursor <= end:
		if skip_holidays and cursor in holiday_set:
			cursor += timedelta(days=1)
			continue
		total += 0.5 if half_on == cursor else 1.0
		cursor += timedelta(days=1)
	return total


def find_overlapping_application(employee: str, start, end, exclude: str | None = None) -> str | None:
	rows = frappe.db.sql(
		"""
		select name from `tabLeave Application`
		where employee = %s and status in ('Open', 'Approved')
			and name != %s
			and from_date <= %s and to_date >= %s
		limit 1
		""",
		(employee, exclude or "", getdate(end), getdate(start)),
	)
	return rows[0][0] if rows else None


def used_days(employee: str, leave_type: str, year: int, statuses: tuple[str, ...], exclude: str | None = None) -> float:
	start, end = year_bounds(year)
	placeholders = ", ".join(["%s"] * len(statuses))
	rows = frappe.db.sql(
		f"""
		select total_days from `tabLeave Application`
		where employee = %s and leave_type = %s and status in ({placeholders})
			and name != %s
			and from_date <= %s and to_date >= %s
		""",
		(employee, leave_type, *statuses, exclude or "", end, start),
	)
	return flt(sum(flt(row[0]) for row in rows))


def allocated_days(employee: str, leave_type: str, year: int) -> float:
	start, end = year_bounds(year)
	rows = frappe.db.sql(
		"""
		select allocated from `tabLeave Allocation`
		where employee = %s and leave_type = %s
			and from_date <= %s and to_date >= %s
		""",
		(employee, leave_type, end, start),
	)
	return flt(sum(flt(row[0]) for row in rows))


def leave_type_dict(name: str) -> dict:
	doc = frappe.get_doc("Leave Type", name)
	return {
		"name": doc.name,
		"is_lwp": int(doc.is_lwp or 0),
		"include_holiday": int(doc.include_holiday or 0),
		"is_active": int(doc.is_active or 0),
		"max_consecutive_days": int(doc.max_consecutive_days or 0),
		"color": doc.color or "#0369A1",
		"company": doc.company,
	}


def load_application(name: str):
	if not name or not frappe.db.exists("Leave Application", name):
		frappe.throw("Leave application not found", frappe.DoesNotExistError)
	# exists() is permission-agnostic; get_doc 404s without select/read.
	# Load via new_doc so Employee can cancel/read their own row, then mark it
	# existing so save() updates instead of inserting a duplicate.
	doc = frappe.new_doc("Leave Application")
	doc.name = name
	doc.load_from_db()
	doc.set("__islocal", 0)
	return doc


def application_dict(doc) -> dict:
	return {
		"name": doc.name,
		"employee": doc.employee,
		"employee_name": doc.employee_name,
		"leave_type": doc.leave_type,
		"from_date": str(getdate(doc.from_date)),
		"to_date": str(getdate(doc.to_date)),
		"half_day": int(doc.half_day or 0),
		"half_day_date": str(getdate(doc.half_day_date)) if doc.half_day_date else None,
		"total_days": flt(doc.total_days),
		"reason": doc.reason,
		"status": doc.status,
		"remarks": doc.remarks,
		"reviewed_by": doc.reviewed_by,
		"reviewed_on": str(doc.reviewed_on) if doc.reviewed_on else None,
	}


def preview_application(
	employee: str,
	company: str | None,
	leave_type: str,
	from_date,
	to_date,
	half_day=0,
	half_day_date=None,
	exclude: str | None = None,
	check_balance: bool = True,
) -> dict:
	if not frappe.db.exists("Leave Type", leave_type):
		frappe.throw("Unknown leave type")
	info = leave_type_dict(leave_type)
	start, end = getdate(from_date), getdate(to_date)
	holidays = company_holiday_dates(company, start, end)
	days = count_leave_days(
		start,
		end,
		half_day=half_day,
		half_day_date=half_day_date,
		include_holiday=info["include_holiday"],
		holidays=holidays,
	)
	if days <= 0:
		frappe.throw("This period does not include any leave days")
	max_days = info["max_consecutive_days"]
	if max_days and days > max_days:
		frappe.throw(f"This leave type allows at most {max_days} day(s) in one application")
	overlap = find_overlapping_application(employee, start, end, exclude=exclude)
	if check_balance and overlap:
		frappe.throw(f"This period overlaps leave application {overlap}")
	year = start.year
	allocated = allocated_days(employee, leave_type, year)
	taken = used_days(employee, leave_type, year, ("Approved",), exclude=exclude)
	pending = used_days(employee, leave_type, year, ("Open",), exclude=exclude)
	available = None if info["is_lwp"] else flt(allocated - taken - pending)
	if check_balance and available is not None and days > available + 1e-9:
		frappe.throw(f"Insufficient balance: {available:g} day(s) available, {days:g} requested")
	return {
		"leave_type": info,
		"from_date": str(start),
		"to_date": str(end),
		"half_day": cint(half_day),
		"half_day_date": str(getdate(half_day_date)) if half_day and half_day_date else (str(start) if cint(half_day) and start == end else None),
		"total_days": days,
		"allocated": allocated,
		"taken": taken,
		"pending": pending,
		"available": available,
		"holidays_skipped": sorted(d.isoformat() for d in holidays) if not info["include_holiday"] else [],
	}


def build_balance(employee: str, company: str | None, year=None) -> dict:
	year = parse_year(year)
	start, end = year_bounds(year)
	holidays = company_holiday_dates(company, start, end)
	names = frappe.get_all("Leave Type", filters={"is_active": 1}, pluck="name", order_by="leave_type_name asc")
	balances = []
	for name in names:
		info = leave_type_dict(name)
		allocated = allocated_days(employee, name, year)
		taken = used_days(employee, name, year, ("Approved",))
		pending = used_days(employee, name, year, ("Open",))
		available = None if info["is_lwp"] else flt(allocated - taken - pending)
		balances.append({**info, "allocated": allocated, "taken": taken, "pending": pending, "available": available})
	return {
		"year": year,
		"from_date": start.isoformat(),
		"to_date": end.isoformat(),
		"holidays": [d.isoformat() for d in sorted(holidays)],
		"balances": balances,
	}
