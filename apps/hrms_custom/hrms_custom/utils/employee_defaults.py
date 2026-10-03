"""Apply Company attendance defaults when an Employee joins or moves company."""

from __future__ import annotations

from datetime import date, timedelta

import frappe
from frappe.utils import add_months, getdate

WEEKDAY_INDEX = {
	"Monday": 0,
	"Tuesday": 1,
	"Wednesday": 2,
	"Thursday": 3,
	"Friday": 4,
	"Saturday": 5,
	"Sunday": 6,
}
ROSTER_WEEK_OFF_MONTHS = 12


def parse_week_off_weekdays(raw: str) -> tuple[list[str], list[str]]:
	"""Return (valid unique weekdays in input order, invalid tokens)."""
	valid: list[str] = []
	seen: set[str] = set()
	invalid: list[str] = []
	for part in (raw or "").replace(";", ",").split(","):
		name = part.strip()
		if not name:
			continue
		# Accept title case or full uppercase
		normalized = name[:1].upper() + name[1:].lower() if name.islower() or name.isupper() else name
		if normalized not in WEEKDAY_INDEX:
			invalid.append(name)
			continue
		if normalized in seen:
			continue
		seen.add(normalized)
		valid.append(normalized)
	return valid, invalid


def week_off_indices_from_company(company) -> set[int]:
	weekdays, _ = parse_week_off_weekdays(getattr(company, "default_week_off_weekdays", None) or "")
	return {WEEKDAY_INDEX[name] for name in weekdays if name in WEEKDAY_INDEX}


def apply_company_defaults(employee, *, is_new: bool = True) -> None:
	"""Shift assignment, holiday list copy, and roster week-offs from Company settings."""
	if not employee.company:
		return
	if not frappe.db.exists("Company", employee.company):
		return

	company = frappe.get_cached_doc("Company", employee.company)
	_apply_holiday_list(employee, company, is_new=is_new)
	_apply_default_shift(employee, company)
	_apply_default_week_offs(employee, company)


def _apply_holiday_list(employee, company, *, is_new: bool) -> None:
	if not company.holiday_list:
		return
	if not is_new and frappe.db.get_value("Employee", employee.name, "holiday_list"):
		return
	frappe.db.set_value("Employee", employee.name, "holiday_list", company.holiday_list, update_modified=False)


def _apply_default_shift(employee, company) -> None:
	if not company.default_shift:
		return
	if not frappe.db.exists("Shift Type", company.default_shift):
		return
	if frappe.db.exists("Shift Assignment", {"employee": employee.name, "status": "Active"}):
		return
	start = getdate(employee.date_of_joining) if employee.date_of_joining else getdate()
	frappe.get_doc(
		{
			"doctype": "Shift Assignment",
			"employee": employee.name,
			"shift_type": company.default_shift,
			"start_date": start,
			"status": "Active",
		}
	).insert(ignore_permissions=True)


def _apply_default_week_offs(employee, company) -> None:
	indices = week_off_indices_from_company(company)
	if not indices:
		return
	start = getdate(employee.date_of_joining) if employee.date_of_joining else getdate()
	end = add_months(start, ROSTER_WEEK_OFF_MONTHS)
	seed_roster_week_offs(employee.name, indices, start, end)


def seed_roster_week_offs(employee: str, weekday_indices: set[int], start: date, end: date) -> int:
	"""Create Shift Roster week-off rows for matching weekdays; skip dates that already have roster."""
	created = 0
	cursor = getdate(start)
	end = getdate(end)
	existing = {
		getdate(row.date)
		for row in frappe.db.sql(
			"""
			select date from `tabShift Roster`
			where employee = %s and date between %s and %s
			""",
			(employee, cursor, end),
			as_dict=True,
		)
	}
	while cursor <= end:
		if cursor.weekday() in weekday_indices and cursor not in existing:
			frappe.get_doc(
				{
					"doctype": "Shift Roster",
					"employee": employee,
					"date": cursor,
					"is_week_off": 1,
				}
			).insert(ignore_permissions=True)
			created += 1
		cursor += timedelta(days=1)
	return created


def holiday_list_for_employee(employee: str, company: str | None) -> str | None:
	list_name = frappe.db.get_value("Employee", employee, "holiday_list")
	if list_name:
		return list_name
	if company:
		return frappe.db.get_value("Company", company, "holiday_list")
	return None
