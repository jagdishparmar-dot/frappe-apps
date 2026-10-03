"""Resolve an employee's shift and holidays for a calendar month."""

from calendar import monthrange
from datetime import date, timedelta

import frappe
from frappe.utils import cint, flt, get_time, getdate

ROSTER_WEEK_OFF = "__WEEK_OFF__"


def parse_month(month: str | None) -> date:
	"""Return the first day of `YYYY-MM`. Defaults to the current month."""
	if not month:
		today = getdate()
		return date(today.year, today.month, 1)
	try:
		year_s, mon_s = str(month).split("-")
		year, mon = int(year_s), int(mon_s)
		if not 1 <= mon <= 12:
			raise ValueError
		return date(year, mon, 1)
	except (TypeError, ValueError):
		frappe.throw("month must be YYYY-MM")


def month_range(first: date) -> tuple[date, date]:
	last = date(first.year, first.month, monthrange(first.year, first.month)[1])
	return first, last


def _time_seconds(value) -> int:
	t = get_time(value)
	if hasattr(t, "total_seconds"):
		return int(t.total_seconds())
	return t.hour * 3600 + t.minute * 60 + getattr(t, "second", 0)


def format_time(value) -> str | None:
	if value in (None, ""):
		return None
	seconds = _time_seconds(value)
	hours, rem = divmod(seconds, 3600)
	minutes, secs = divmod(rem, 60)
	return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def times_are_overnight(start, end) -> bool:
	return _time_seconds(end) < _time_seconds(start)


def shift_duration_hours(start, end) -> float:
	started = _time_seconds(start)
	ended = _time_seconds(end)
	if ended <= started:
		ended += 24 * 3600
	return round((ended - started) / 3600, 2)


def shift_type_dict(doc) -> dict:
	start = format_time(doc.start_time)
	end = format_time(doc.end_time)
	overnight = bool(cint(getattr(doc, "is_overnight", 0))) or bool(start and end and times_are_overnight(doc.start_time, doc.end_time))
	working = flt(getattr(doc, "working_hours", 0))
	if not working and doc.start_time and doc.end_time:
		working = shift_duration_hours(doc.start_time, doc.end_time)
	return {
		"name": doc.name,
		"start_time": start,
		"end_time": end,
		"grace_minutes": int(doc.grace_minutes or 0),
		"early_exit_grace_minutes": int(getattr(doc, "early_exit_grace_minutes", 0) or 0),
		"working_hours": working,
		"minimum_hours_present": flt(getattr(doc, "minimum_hours_present", 0)),
		"minimum_hours_half_day": flt(getattr(doc, "minimum_hours_half_day", 0)),
		"allow_flexible_hours": int(getattr(doc, "allow_flexible_hours", 0) or 0),
		"color": doc.color or "#1F5EFF",
		"location": doc.location,
		"company": doc.company,
		"holiday_list": doc.holiday_list,
		"is_active": int(doc.is_active or 0),
		"is_overnight": overnight,
	}


def holidays_between(list_names: list[str], start: date, end: date) -> dict[date, dict]:
	result: dict[date, dict] = {}
	for name in dict.fromkeys(n for n in list_names if n):
		if not frappe.db.exists("Holiday List", name):
			continue
		doc = frappe.get_doc("Holiday List", name)
		for row in doc.holidays:
			day = getdate(row.holiday_date)
			if start <= day <= end:
				result[day] = {"description": row.description, "weekly_off": int(row.weekly_off or 0)}
	return result


def shift_for_day(employee: str, day: date | None = None) -> dict | None:
	"""Roster wins over an active assignment for a single calendar day."""
	day = day or getdate()
	roster = rosters_between(employee, day, day).get(day)
	assignment = assignment_covering(employee, day)
	types = load_shift_types(
		[
			roster.shift_type if roster else None,
			assignment.shift_type if assignment else None,
		]
	)
	if roster and cint(roster.get("is_week_off")):
		return None
	if roster and roster.shift_type in types:
		return shift_payload(
			types[roster.shift_type],
			assignment=assignment.name if assignment else None,
			roster=roster.name,
			location=roster.location,
		)
	if assignment and assignment.shift_type in types:
		return shift_payload(types[assignment.shift_type], assignment=assignment.name)
	return None


def assignment_covering(employee: str, day: date) -> dict | None:
	rows = frappe.db.sql(
		"""
		select name, shift_type from `tabShift Assignment`
		where employee = %s and status = 'Active'
			and start_date <= %s
			and ifnull(end_date, '9999-12-31') >= %s
		order by start_date desc
		limit 1
		""",
		(employee, day, day),
		as_dict=True,
	)
	return rows[0] if rows else None


def rosters_between(employee: str, start: date, end: date) -> dict[date, dict]:
	rows = frappe.db.sql(
		"""
		select name, date, shift_type, location, is_week_off from `tabShift Roster`
		where employee = %s and date between %s and %s
		""",
		(employee, start, end),
		as_dict=True,
	)
	return {getdate(row.date): row for row in rows}


def roster_week_offs_between(employees: list[str], start: date, end: date) -> dict[str, set[date]]:
	"""Per-employee dates marked week off on Shift Roster."""
	result: dict[str, set[date]] = {name: set() for name in employees}
	if not employees:
		return result
	for row in frappe.db.sql(
		"""
		select employee, date from `tabShift Roster`
		where employee in %(employees)s and date between %(start)s and %(end)s
			and is_week_off = 1
		""",
		{"employees": employees, "start": start, "end": end},
		as_dict=True,
	):
		result.setdefault(row.employee, set()).add(getdate(row.date))
	return result


def shift_payload(type_info: dict, *, assignment=None, roster=None, location=None) -> dict:
	info = dict(type_info)
	info["assignment"] = assignment
	info["roster"] = roster
	info["source"] = "roster" if roster else "assignment"
	if location:
		info["location"] = location
	return info


def load_shift_types(names: list[str]) -> dict[str, dict]:
	return {
		name: shift_type_dict(frappe.get_doc("Shift Type", name))
		for name in dict.fromkeys(n for n in names if n)
		if frappe.db.exists("Shift Type", name)
	}


def assignment_on(assignments: list, day: date):
	return next(
		(
			row
			for row in reversed(assignments)
			if getdate(row.start_date) <= day <= getdate(row.end_date or "9999-12-31")
		),
		None,
	)


def build_calendar(employee: str, company: str | None, month: str | None) -> dict:
	first, last = month_range(parse_month(month))
	from hrms_custom.utils.employee_defaults import holiday_list_for_employee

	employee_list = holiday_list_for_employee(employee, company)
	assignments = frappe.db.sql(
		"""
		select name, shift_type, start_date, end_date from `tabShift Assignment`
		where employee = %s and status = 'Active'
			and start_date <= %s
			and ifnull(end_date, '9999-12-31') >= %s
		order by start_date
		""",
		(employee, last, first),
		as_dict=True,
	)
	rosters = rosters_between(employee, first, last)
	types = load_shift_types([*(a.shift_type for a in assignments), *(r.shift_type for r in rosters.values())])
	holiday_lists = [employee_list, *[types[n].get("holiday_list") for n in types]]
	holidays = holidays_between(holiday_lists, first, last)

	days = {}
	cursor = first
	while cursor <= last:
		key = cursor.isoformat()
		assignment = assignment_on(assignments, cursor)
		roster = rosters.get(cursor)
		shift = None
		week_off = bool(roster and cint(roster.get("is_week_off")))
		if roster and not week_off and roster.shift_type in types:
			shift = shift_payload(
				types[roster.shift_type],
				assignment=assignment.name if assignment else None,
				roster=roster.name,
				location=roster.location,
			)
		elif not week_off and assignment and assignment.shift_type in types:
			shift = shift_payload(types[assignment.shift_type], assignment=assignment.name)
		holiday = holidays.get(cursor)
		if holiday or shift or week_off:
			entry = {
				"date": key,
				"is_holiday": bool(holiday),
				"is_week_off": int(week_off),
				"holiday": holiday,
			}
			if shift:
				entry["shift"] = shift
			days[key] = entry
		cursor += timedelta(days=1)

	return {
		"month": f"{first.year:04d}-{first.month:02d}",
		"from_date": first.isoformat(),
		"to_date": last.isoformat(),
		"employee": employee,
		"days": days,
	}


def parse_entries(value) -> list:
	if value in (None, ""):
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value)
	if not isinstance(value, list):
		frappe.throw("entries must be a list")
	return value


def build_roster(month: str | None, department: str | None = None, company: str | None = None) -> dict:
	first, last = month_range(parse_month(month))
	filters: dict = {"status": "Active"}
	if department:
		if not frappe.db.exists("Department", department):
			frappe.throw("Unknown department")
		filters["department"] = department
	if company:
		if not frappe.db.exists("Company", company):
			frappe.throw("Unknown company")
		filters["company"] = company

	employees = frappe.get_all(
		"Employee",
		filters=filters,
		fields=["name", "employee_name", "department", "company"],
		order_by="employee_name asc",
		limit=500,
	)
	names = [row.name for row in employees]
	assignments = []
	rosters = []
	if names:
		assignments = frappe.db.sql(
			"""
			select name, employee, shift_type, start_date, end_date
			from `tabShift Assignment`
			where employee in %(employees)s and status = 'Active'
				and start_date <= %(last)s
				and ifnull(end_date, '9999-12-31') >= %(first)s
			order by start_date
			""",
			{"employees": names, "first": first, "last": last},
			as_dict=True,
		)
		rosters = frappe.db.sql(
			"""
			select name, employee, date, shift_type, location, is_week_off
			from `tabShift Roster`
			where employee in %(employees)s and date between %(first)s and %(last)s
			""",
			{"employees": names, "first": first, "last": last},
			as_dict=True,
		)

	used_types = [*(a.shift_type for a in assignments), *(r.shift_type for r in rosters if r.shift_type)]
	active_names = frappe.get_all("Shift Type", filters={"is_active": 1}, pluck="name", order_by="shift_name asc")
	types = load_shift_types([*active_names, *used_types])
	from hrms_custom.utils.employee_defaults import holiday_list_for_employee

	holiday_lists = [holiday_list_for_employee(row.name, row.company) for row in employees]
	holidays = holidays_between(holiday_lists, first, last)

	roster_map: dict[tuple[str, date], dict] = {
		(row.employee, getdate(row.date)): row for row in rosters
	}
	assignment_by_employee: dict[str, list] = {}
	for row in assignments:
		assignment_by_employee.setdefault(row.employee, []).append(row)

	cells: dict[str, dict] = {}
	cursor = first
	while cursor <= last:
		key = cursor.isoformat()
		for emp in names:
			roster = roster_map.get((emp, cursor))
			assignment = assignment_on(assignment_by_employee.get(emp, []), cursor)
			cell = None
			if roster and cint(roster.get("is_week_off")):
				cell = {
					"shift_type": ROSTER_WEEK_OFF,
					"is_week_off": 1,
					"source": "roster",
					"roster": roster.name,
					"assignment": assignment.name if assignment else None,
				}
			elif roster and roster.shift_type in types:
				cell = {
					"shift_type": roster.shift_type,
					"location": roster.location or types[roster.shift_type].get("location"),
					"source": "roster",
					"roster": roster.name,
					"assignment": assignment.name if assignment else None,
				}
			elif assignment and assignment.shift_type in types:
				cell = {
					"shift_type": assignment.shift_type,
					"location": types[assignment.shift_type].get("location"),
					"source": "assignment",
					"roster": None,
					"assignment": assignment.name,
				}
			if cell:
				cells.setdefault(emp, {})[key] = cell
		cursor += timedelta(days=1)

	days = []
	cursor = first
	while cursor <= last:
		holiday = holidays.get(cursor)
		days.append(
			{
				"date": cursor.isoformat(),
				"weekday": cursor.strftime("%a"),
				"is_holiday": bool(holiday),
				"holiday": holiday,
			}
		)
		cursor += timedelta(days=1)

	return {
		"month": f"{first.year:04d}-{first.month:02d}",
		"from_date": first.isoformat(),
		"to_date": last.isoformat(),
		"department": department,
		"company": company,
		"shift_types": [types[name] for name in active_names if name in types],
		"days": days,
		"employees": employees,
		"cells": cells,
	}
