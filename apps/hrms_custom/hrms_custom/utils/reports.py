"""Shared filters and row builders for the V1 Desk reports."""

from datetime import date, datetime, time, timedelta

import frappe
from frappe.utils import cint, flt, get_datetime, get_time, getdate

from hrms_custom.utils.leave import allocated_days, company_holiday_dates, leave_type_dict, parse_year, used_days
from hrms_custom.utils.shifts import assignment_on, load_shift_types, month_range, parse_month, shift_payload


def parse_day(value) -> date:
	if value in (None, ""):
		return getdate()
	try:
		return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
	except ValueError:
		frappe.throw("date must be YYYY-MM-DD")


def parse_date_range(filters: dict | None) -> tuple[date, date]:
	filters = filters or {}
	if filters.get("month"):
		return month_range(parse_month(filters.get("month")))
	start = getdate(filters["from_date"]) if filters.get("from_date") else None
	end = getdate(filters["to_date"]) if filters.get("to_date") else None
	if not start or not end:
		return month_range(parse_month(None))
	if end < start:
		frappe.throw("To date cannot be before from date")
	if (end - start).days > 366:
		frappe.throw("Date range cannot exceed one year")
	return start, end


def list_employees(filters: dict | None, *, status: str | None = None) -> list[dict]:
	filters = filters or {}
	query: dict = {}
	if status:
		query["status"] = status
	elif filters.get("status"):
		query["status"] = filters["status"]
	if filters.get("company"):
		if not frappe.db.exists("Company", filters["company"]):
			frappe.throw("Unknown company")
		query["company"] = filters["company"]
	if filters.get("department"):
		if not frappe.db.exists("Department", filters["department"]):
			frappe.throw("Unknown department")
		query["department"] = filters["department"]
	if filters.get("employee"):
		if not frappe.db.exists("Employee", filters["employee"]):
			frappe.throw("Unknown employee")
		query["name"] = filters["employee"]
	if filters.get("onboarding_status"):
		query["onboarding_status"] = filters["onboarding_status"]
	if filters.get("employee_type"):
		query["employee_type"] = filters["employee_type"]
	if filters.get("vendor"):
		if not frappe.db.exists("Vendor", filters["vendor"]):
			frappe.throw("Unknown vendor")
		query["vendor"] = filters["vendor"]
	return frappe.get_all(
		"Employee",
		filters=query,
		fields=[
			"name",
			"employee_name",
			"company",
			"department",
			"designation",
			"branch",
			"status",
			"onboarding_status",
			"employee_type",
			"vendor",
			"other_employee_type",
			"date_of_joining",
			"relieving_date",
			"cell_number",
			"personal_email",
			"company_email",
			"user_id",
		],
		order_by="employee_name asc",
		limit=1000,
	)


def _time_on(day: date, time_value) -> datetime:
	t = get_time(time_value)
	seconds = int(t.total_seconds()) if hasattr(t, "total_seconds") else t.hour * 3600 + t.minute * 60 + getattr(t, "second", 0)
	hours, rem = divmod(seconds, 3600)
	minutes, secs = divmod(rem, 60)
	return datetime(day.year, day.month, day.day, hours, minutes, secs)


def shift_window(day: date, shift: dict) -> tuple[datetime, datetime, datetime]:
	start = _time_on(day, shift["start_time"])
	end = _time_on(day + timedelta(days=1) if shift.get("is_overnight") else day, shift["end_time"])
	late_after = start + timedelta(minutes=int(shift.get("grace_minutes") or 0))
	return start, end, late_after


def _load_shifts_for(employees: list[dict], start: date, end: date) -> dict[str, dict]:
	names = [row.name for row in employees]
	assignments: dict[str, list] = {}
	rosters: dict[str, dict] = {}
	if names:
		for row in frappe.db.sql(
			"""
			select name, employee, shift_type, start_date, end_date
			from `tabShift Assignment`
			where employee in %(employees)s and status = 'Active'
				and start_date <= %(end)s
				and ifnull(end_date, '9999-12-31') >= %(start)s
			order by start_date
			""",
			{"employees": names, "start": start, "end": end},
			as_dict=True,
		):
			assignments.setdefault(row.employee, []).append(row)
		for row in frappe.db.sql(
			"""
			select name, employee, date, shift_type, location
			from `tabShift Roster`
			where employee in %(employees)s and date between %(start)s and %(end)s
			""",
			{"employees": names, "start": start, "end": end},
			as_dict=True,
		):
			rosters.setdefault(row.employee, {})[getdate(row.date)] = row
	types = load_shift_types(
		[*(a.shift_type for rows in assignments.values() for a in rows), *(r.shift_type for days in rosters.values() for r in days.values())]
	)
	resolved: dict[str, dict] = {}
	for emp in names:
		by_day = {}
		cursor = start
		while cursor <= end:
			roster = rosters.get(emp, {}).get(cursor)
			assignment = assignment_on(assignments.get(emp, []), cursor)
			shift = None
			if roster and roster.shift_type in types:
				shift = shift_payload(types[roster.shift_type], assignment=assignment.name if assignment else None, roster=roster.name, location=roster.location)
			elif assignment and assignment.shift_type in types:
				shift = shift_payload(types[assignment.shift_type], assignment=assignment.name)
			if shift:
				by_day[cursor] = shift
			cursor += timedelta(days=1)
		resolved[emp] = by_day
	return resolved


def _load_checkins(employees: list[str], start: date, end: date) -> dict[str, list]:
	if not employees:
		return {}
	rows = frappe.db.sql(
		"""
		select name, employee, employee_name, log_type, time, latitude, longitude,
			is_within_geofence, geofence_location, distance_from_geofence, is_auto_closed, device_id
		from `tabEmployee Checkin`
		where employee in %(employees)s
			and time >= %(start)s and time < %(end)s
		order by time
		""",
		{"employees": employees, "start": start, "end": end + timedelta(days=2)},
		as_dict=True,
	)
	grouped: dict[str, list] = {}
	for row in rows:
		grouped.setdefault(row.employee, []).append(row)
	return grouped


def punch_search_window(day: date, shift: dict | None) -> tuple[datetime, datetime]:
	"""IN/OUT search range for a shift date, including slack around overnight windows."""
	if shift:
		start, end, _ = shift_window(day, shift)
		slack = timedelta(hours=4)
		return start - slack, end + slack
	start = datetime.combine(day, time.min)
	return start, start + timedelta(days=1)


def _first_in(punches: list, day: date, shift: dict | None = None):
	lo, hi = punch_search_window(day, shift)
	ins = [p for p in punches if p.log_type == "IN" and lo <= get_datetime(p.time) <= hi]
	return min(ins, key=lambda p: get_datetime(p.time)) if ins else None


def _last_out(punches: list, day: date, shift: dict | None = None, after=None):
	lo, hi = punch_search_window(day, shift)
	opened = get_datetime(after.time) if after else lo
	outs = [p for p in punches if p.log_type == "OUT" and opened <= get_datetime(p.time) <= hi]
	return max(outs, key=lambda p: get_datetime(p.time)) if outs else None


def _pair_punches(punches: list, day: date, shift: dict | None = None):
	first = _first_in(punches, day, shift)
	return first, _last_out(punches, day, shift, after=first)


def _approved_leave_days(employees: list[str], start: date, end: date, company_holidays: dict[str, set[date]]) -> dict[str, set[date]]:
	covered: dict[str, set[date]] = {name: set() for name in employees}
	if not employees:
		return covered
	rows = frappe.db.sql(
		"""
		select employee, leave_type, from_date, to_date, half_day, half_day_date
		from `tabLeave Application`
		where employee in %(employees)s and status = 'Approved'
			and from_date <= %(end)s and to_date >= %(start)s
		""",
		{"employees": employees, "start": start, "end": end},
		as_dict=True,
	)
	types = {name: leave_type_dict(name) for name in {row.leave_type for row in rows}}
	for row in rows:
		info = types[row.leave_type]
		holidays = set() if info["include_holiday"] else company_holidays.get(row.employee, set())
		cursor = max(getdate(row.from_date), start)
		last = min(getdate(row.to_date), end)
		half_on = getdate(row.half_day_date) if row.half_day and row.half_day_date else (getdate(row.from_date) if row.half_day else None)
		while cursor <= last:
			if cursor not in holidays:
				covered[row.employee].add(cursor)
			elif half_on == cursor:
				covered[row.employee].add(cursor)
			cursor += timedelta(days=1)
	return covered


def _employed_on(employee: dict, day: date) -> bool:
	joined = getdate(employee.date_of_joining) if employee.date_of_joining else None
	left = getdate(employee.relieving_date) if employee.relieving_date else None
	if joined and day < joined:
		return False
	if left and day > left:
		return False
	return True


def attendance_summary_rows(filters: dict | None) -> list[dict]:
	start, end = parse_date_range({**(filters or {}), "month": (filters or {}).get("month")})
	employees = list_employees(filters, status="Active")
	shifts = _load_shifts_for(employees, start, end)
	checkins = _load_checkins([row.name for row in employees], start, end)
	holiday_by_company: dict[str, set[date]] = {}
	holiday_by_employee: dict[str, set[date]] = {}
	for emp in employees:
		if emp.company not in holiday_by_company:
			holiday_by_company[emp.company] = company_holiday_dates(emp.company, start, end)
		holiday_by_employee[emp.name] = holiday_by_company.get(emp.company) or set()
	leave_days = _approved_leave_days([row.name for row in employees], start, end, holiday_by_employee)
	today = getdate()

	rows = []
	for emp in employees:
		present = absent = late = on_leave = half_day = 0
		cursor = start
		while cursor <= end:
			if not _employed_on(emp, cursor):
				cursor += timedelta(days=1)
				continue
			holiday = cursor in holiday_by_employee[emp.name]
			on_leave_today = cursor in leave_days.get(emp.name, set())
			shift = shifts.get(emp.name, {}).get(cursor)
			first, last = _pair_punches(checkins.get(emp.name, []), cursor, shift)
			status, is_late = _day_attendance_status(
				first, last, shift, holiday, on_leave_today, cursor, today, calendar=False
			)
			if status in ("Present", "Late"):
				present += 1
			elif status == "Half Day":
				half_day += 1
			elif status == "Absent":
				absent += 1
			if is_late and status in ("Present", "Late", "Half Day"):
				late += 1
			if on_leave_today:
				on_leave += 1
			cursor += timedelta(days=1)
		rows.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
				"company": emp.company,
				"present": present,
				"absent": absent,
				"late": late,
				"half_day": half_day,
				"on_leave": on_leave,
			}
		)
	return rows


def live_attendance(filters: dict | None) -> dict:
	"""One-day present / absent / late / on-leave snapshot for the HR dashboard."""
	filters = filters or {}
	day = parse_day(filters.get("date"))
	employees = list_employees(filters, status="Active")
	shifts = _load_shifts_for(employees, day, day)
	checkins = _load_checkins([row.name for row in employees], day, day)
	holiday_by_company: dict[str, set[date]] = {}
	holiday_by_employee: dict[str, set[date]] = {}
	for emp in employees:
		if emp.company not in holiday_by_company:
			holiday_by_company[emp.company] = company_holiday_dates(emp.company, day, day)
		holiday_by_employee[emp.name] = holiday_by_company.get(emp.company) or set()
	leave_days = _approved_leave_days([row.name for row in employees], day, day, holiday_by_employee)

	counts = {"present": 0, "absent": 0, "late": 0, "half_day": 0, "on_leave": 0}
	rows = []
	for emp in employees:
		if not _employed_on(emp, day):
			continue
		holiday = day in holiday_by_employee[emp.name]
		on_leave_today = day in leave_days.get(emp.name, set())
		shift = shifts.get(emp.name, {}).get(day)
		punches = checkins.get(emp.name, [])
		first, last = _pair_punches(punches, day, shift)
		status, late = _day_attendance_status(
			first, last, shift, holiday, on_leave_today, day, day, calendar=False
		)
		if status in ("Present", "Late"):
			counts["present"] += 1
		elif status == "Half Day":
			counts["half_day"] += 1
		elif status == "Absent":
			counts["absent"] += 1
		if late and status in ("Present", "Late", "Half Day"):
			counts["late"] += 1
		if on_leave_today:
			counts["on_leave"] += 1
		rows.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"department": emp.department,
				"company": emp.company,
				"status": status,
				"in_time": str(get_datetime(first.time)) if first else None,
				"out_time": str(get_datetime(last.time)) if last else None,
				"shift_type": shift["name"] if shift else None,
				"is_holiday": int(holiday),
				"on_leave": int(on_leave_today),
				"is_late": int(late),
				"is_within_geofence": int(first.is_within_geofence) if first and first.is_within_geofence is not None else None,
			}
		)
	order = {"Late": 0, "Present": 1, "Half Day": 2, "On Leave": 3, "Holiday": 4, "Absent": 5}
	rows.sort(key=lambda row: (order.get(row["status"], 9), (row["employee_name"] or row["employee"]).lower()))
	return {
		"date": day.isoformat(),
		"company": filters.get("company"),
		"department": filters.get("department"),
		"counts": counts,
		"headcount": len(rows),
		"employees": rows,
	}


def _worked_minutes(first, last) -> int | None:
	if not first or not last:
		return None
	delta = get_datetime(last.time) - get_datetime(first.time)
	if delta.total_seconds() < 0:
		return None
	return int(delta.total_seconds() // 60)


def _worked_label(minutes: int | None) -> str | None:
	if minutes is None:
		return None
	hours, mins = divmod(minutes, 60)
	if hours and mins:
		return f"{hours}h {mins}m"
	if hours:
		return f"{hours}h"
	return f"{mins}m"


def _hours_to_minutes(value) -> int | None:
	hours = flt(value)
	if hours <= 0:
		return None
	return int(round(hours * 60))


def _status_from_hours(worked_minutes: int | None, shift: dict | None, late: bool) -> str:
	present_m = _hours_to_minutes(shift.get("minimum_hours_present") if shift else None)
	half_m = _hours_to_minutes(shift.get("minimum_hours_half_day") if shift else None)
	flexible = bool(shift and cint(shift.get("allow_flexible_hours")))
	if worked_minutes is not None and (present_m is not None or half_m is not None):
		if present_m is not None and worked_minutes >= present_m:
			return "Present" if flexible or not late else "Late"
		if half_m is not None and worked_minutes >= half_m:
			return "Half Day"
		return "Absent"
	if late and not flexible:
		return "Late"
	return "Present"


def _day_attendance_status(
	first, last, shift, holiday: bool, on_leave: bool, day, today, *, calendar=True
) -> tuple[str, bool]:
	late = False
	if first and shift:
		_, _, late_after = shift_window(day, shift)
		late = get_datetime(first.time) > late_after
	if first:
		return _status_from_hours(_worked_minutes(first, last), shift, late), late
	if on_leave:
		return "On Leave", False
	if holiday:
		return "Holiday", False
	if calendar:
		if day > today:
			return "Upcoming", False
		if day == today:
			return "Pending", False
	return "Absent", False


def employee_date_attendance_rows(filters: dict | None) -> list[dict]:
	"""One row per employee per day: identity, date, IN/OUT, hours, and present/absent/leave status.

	`month` (YYYY-MM) wins over `from_date`/`to_date`. Either filter set is optional; the default
	is the current calendar month.
	"""
	start, end = parse_date_range(filters)
	today = getdate()
	employees = list_employees(filters, status="Active")
	shifts = _load_shifts_for(employees, start, end)
	checkins = _load_checkins([row.name for row in employees], start, end)
	holiday_by_company: dict[str, set[date]] = {}
	holiday_by_employee: dict[str, set[date]] = {}
	for emp in employees:
		if emp.company not in holiday_by_company:
			holiday_by_company[emp.company] = company_holiday_dates(emp.company, start, end)
		holiday_by_employee[emp.name] = holiday_by_company.get(emp.company) or set()
	leave_days = _approved_leave_days([row.name for row in employees], start, end, holiday_by_employee)

	rows = []
	for emp in employees:
		cursor = start
		while cursor <= end:
			if not _employed_on(emp, cursor):
				cursor += timedelta(days=1)
				continue
			holiday = cursor in holiday_by_employee[emp.name]
			on_leave_today = cursor in leave_days.get(emp.name, set())
			shift = shifts.get(emp.name, {}).get(cursor)
			punches = checkins.get(emp.name, [])
			first, last = _pair_punches(punches, cursor, shift)
			status, late = _day_attendance_status(first, last, shift, holiday, on_leave_today, cursor, today)
			worked = _worked_minutes(first, last)
			rows.append(
				{
					"employee": emp.name,
					"employee_name": emp.employee_name,
					"company": emp.company,
					"department": emp.department,
					"designation": emp.designation,
					"branch": emp.branch,
					"date": cursor.isoformat(),
					"status": status,
					"in_time": get_datetime(first.time) if first else None,
					"out_time": get_datetime(last.time) if last else None,
					"worked_hours": _worked_label(worked),
					"worked_minutes": worked,
					"shift_type": shift["name"] if shift else None,
					"is_holiday": int(holiday),
					"on_leave": int(on_leave_today),
					"is_late": int(late),
				}
			)
			cursor += timedelta(days=1)
	return rows


def employee_month_attendance(employee: str, month: str | None = None) -> dict:
	"""Month of daily status / times / worked hours for one employee (mobile attendance view)."""
	start, end = month_range(parse_month(month))
	today = getdate()
	employees = list_employees({"employee": employee})
	if not employees:
		frappe.throw("Employee not found")
	emp = employees[0]
	shifts = _load_shifts_for(employees, start, end)
	checkins = _load_checkins([emp.name], start, end)
	holidays = company_holiday_dates(emp.company, start, end)
	leave_days = _approved_leave_days([emp.name], start, end, {emp.name: holidays})

	counts = {"present": 0, "absent": 0, "late": 0, "half_day": 0, "on_leave": 0, "holiday": 0}
	days = {}
	cursor = start
	while cursor <= end:
		if not _employed_on(emp, cursor):
			cursor += timedelta(days=1)
			continue
		holiday = cursor in holidays
		on_leave_today = cursor in leave_days.get(emp.name, set())
		shift = shifts.get(emp.name, {}).get(cursor)
		punches = checkins.get(emp.name, [])
		first, last = _pair_punches(punches, cursor, shift)
		status, late = _day_attendance_status(first, last, shift, holiday, on_leave_today, cursor, today)
		if cursor <= today:
			if status in ("Present", "Late"):
				counts["present"] += 1
			elif status == "Half Day":
				counts["half_day"] += 1
			elif status == "Absent":
				counts["absent"] += 1
			if late and status in ("Present", "Late", "Half Day"):
				counts["late"] += 1
			if on_leave_today:
				counts["on_leave"] += 1
			if holiday:
				counts["holiday"] += 1
		worked = _worked_minutes(first, last)
		days[cursor.isoformat()] = {
			"date": cursor.isoformat(),
			"status": status,
			"in_time": str(get_datetime(first.time)) if first else None,
			"out_time": str(get_datetime(last.time)) if last else None,
			"worked_minutes": worked,
			"worked_hours": _worked_label(worked),
			"shift_type": shift["name"] if shift else None,
			"is_holiday": int(holiday),
			"on_leave": int(on_leave_today),
			"is_late": int(late),
		}
		cursor += timedelta(days=1)
	return {
		"month": f"{start.year:04d}-{start.month:02d}",
		"employee": emp.name,
		"employee_name": emp.employee_name,
		"counts": counts,
		"days": days,
	}


def punch_log_rows(filters: dict | None) -> list[dict]:
	start, end = parse_date_range(filters)
	employees = list_employees(filters)
	names = [row.name for row in employees]
	if not names:
		return []
	conditions = ["employee in %(employees)s", "time >= %(start)s", "time < %(end)s"]
	values = {"employees": names, "start": start, "end": end + timedelta(days=1)}
	flag = (filters or {}).get("within_geofence")
	if flag in ("Yes", "1", 1):
		conditions.append("is_within_geofence = 1")
	elif flag in ("No", "0", 0):
		conditions.append("is_within_geofence = 0")
	rows = frappe.db.sql(
		f"""
		select name, employee, employee_name, log_type, time, latitude, longitude,
			is_within_geofence, geofence_location, distance_from_geofence, is_auto_closed, device_id
		from `tabEmployee Checkin`
		where {" and ".join(conditions)}
		order by time desc
		""",
		values,
		as_dict=True,
	)
	return rows


def leave_balance_rows(filters: dict | None) -> list[dict]:
	year = parse_year((filters or {}).get("year"))
	employees = list_employees(filters)
	leave_type = (filters or {}).get("leave_type")
	if leave_type and not frappe.db.exists("Leave Type", leave_type):
		frappe.throw("Unknown leave type")
	names = frappe.get_all(
		"Leave Type",
		filters={"is_active": 1, **({"name": leave_type} if leave_type else {})},
		pluck="name",
		order_by="leave_type_name asc",
	)
	rows = []
	for emp in employees:
		for name in names:
			info = leave_type_dict(name)
			allocated = allocated_days(emp.name, name, year)
			taken = used_days(emp.name, name, year, ("Approved",))
			pending = used_days(emp.name, name, year, ("Open",))
			available = None if info["is_lwp"] else flt(allocated - taken - pending)
			if allocated == 0 and taken == 0 and pending == 0 and leave_type is None:
				continue
			rows.append(
				{
					"employee": emp.name,
					"employee_name": emp.employee_name,
					"department": emp.department,
					"leave_type": name,
					"is_lwp": info["is_lwp"],
					"allocated": allocated,
					"taken": taken,
					"pending": pending,
					"available": available,
					"year": year,
				}
			)
	return rows


def employee_master_rows(filters: dict | None) -> list[dict]:
	return list_employees(filters)


def late_early_rows(filters: dict | None) -> list[dict]:
	start, end = parse_date_range(filters)
	employees = list_employees(filters, status="Active")
	shifts = _load_shifts_for(employees, start, end)
	checkins = _load_checkins([row.name for row in employees], start, end)
	rows = []
	for emp in employees:
		cursor = start
		while cursor <= end:
			if not _employed_on(emp, cursor):
				cursor += timedelta(days=1)
				continue
			shift = shifts.get(emp.name, {}).get(cursor)
			if not shift:
				cursor += timedelta(days=1)
				continue
			_, shift_end, late_after = shift_window(cursor, shift)
			first, last = _pair_punches(checkins.get(emp.name, []), cursor, shift)
			late_minutes = 0
			early_minutes = 0
			early_after = shift_end - timedelta(minutes=int(shift.get("early_exit_grace_minutes") or 0))
			if first and get_datetime(first.time) > late_after:
				late_minutes = int((get_datetime(first.time) - late_after).total_seconds() // 60)
			if last and get_datetime(last.time) < early_after:
				early_minutes = int((shift_end - get_datetime(last.time)).total_seconds() // 60)
			if late_minutes or early_minutes:
				rows.append(
					{
						"employee": emp.name,
						"employee_name": emp.employee_name,
						"department": emp.department,
						"date": cursor.isoformat(),
						"shift_type": shift["name"],
						"in_time": get_datetime(first.time) if first else None,
						"out_time": get_datetime(last.time) if last else None,
						"late_minutes": late_minutes,
						"early_minutes": early_minutes,
					}
				)
			cursor += timedelta(days=1)
	return rows


def onboarding_status_rows(filters: dict | None) -> list[dict]:
	employees = list_employees(filters)
	names = [row.name for row in employees]
	checklists = {}
	if names:
		for row in frappe.get_all(
			"Onboarding Checklist",
			filters={"employee": ["in", names]},
			fields=["employee", "name", "status"],
		):
			checklists[row.employee] = row
	docs: dict[str, dict[str, int]] = {}
	if names:
		for row in frappe.db.sql(
			"""
			select employee, status, count(*) as n
			from `tabEmployee Document`
			where employee in %(employees)s
			group by employee, status
			""",
			{"employees": names},
			as_dict=True,
		):
			docs.setdefault(row.employee, {})[row.status] = int(row.n)
	rows = []
	for emp in employees:
		if not emp.onboarding_status and (filters or {}).get("onboarding_status"):
			continue
		if (filters or {}).get("checklist_status"):
			cl = checklists.get(emp.name)
			if not cl or cl.status != filters["checklist_status"]:
				continue
		counts = docs.get(emp.name, {})
		cl = checklists.get(emp.name)
		rows.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"company": emp.company,
				"department": emp.department,
				"date_of_joining": emp.date_of_joining,
				"onboarding_status": emp.onboarding_status,
				"status": emp.status,
				"checklist": cl.name if cl else None,
				"checklist_status": cl.status if cl else None,
				"documents_pending": counts.get("Pending", 0),
				"documents_verified": counts.get("Verified", 0),
				"documents_rejected": counts.get("Rejected", 0),
			}
		)
	return rows
