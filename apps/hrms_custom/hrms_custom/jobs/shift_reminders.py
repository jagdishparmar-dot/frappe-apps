"""Remind employees shortly before their shift starts and ends."""

from datetime import timedelta

import frappe
from frappe.utils import cint, get_datetime, getdate, now_datetime

from hrms_custom.utils.notify import CHANNEL_SHIFT_END, CHANNEL_SHIFT_START, notify_employee
from hrms_custom.utils.reports import shift_window
from hrms_custom.utils.shifts import shift_for_day

DEFAULT_LEAD_MINUTES = 15


def send_shift_reminders(now=None) -> dict[str, int]:
	now = get_datetime(now) if now else now_datetime()
	lead = cint(frappe.db.get_single_value("HRMS Custom Settings", "shift_reminder_minutes")) or DEFAULT_LEAD_MINUTES
	counts = {CHANNEL_SHIFT_START: 0, CHANNEL_SHIFT_END: 0}
	today = getdate(now)
	employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")
	for employee in employees:
		_consider(employee, today, now, lead, counts)
		_consider(employee, today - timedelta(days=1), now, lead, counts)
	return counts


def _consider(employee: str, day, now, lead: int, counts: dict[str, int]):
	shift = shift_for_day(employee, day)
	if not shift or not shift.get("start_time") or not shift.get("end_time"):
		return
	start, end, _ = shift_window(day, shift)
	punches = _punch_flags(employee, day)
	label = shift.get("name") or "your shift"
	if _in_lead(start, now, lead) and not punches["in"]:
		key = f"{day.isoformat()}:start"
		if _notify_once(employee, CHANNEL_SHIFT_START, key, "Shift starting soon", f"{label} starts at {_clock(start)}.", "/shifts"):
			counts[CHANNEL_SHIFT_START] += 1
	if _in_lead(end, now, lead) and not punches["out"]:
		key = f"{day.isoformat()}:end"
		if _notify_once(
			employee,
			CHANNEL_SHIFT_END,
			key,
			"Shift ending soon",
			f"{label} ends at {_clock(end)}. Don't forget to punch out.",
			"/",
		):
			counts[CHANNEL_SHIFT_END] += 1


def _notify_once(employee: str, channel: str, key: str, title: str, body: str, route: str) -> bool:
	if frappe.db.exists("Employee Notification", {"employee": employee, "channel": channel, "occurrence_key": key}):
		return False
	return bool(
		notify_employee(employee, channel, title, body, route=route, occurrence_key=key)
	)


def _in_lead(event, now, lead: int) -> bool:
	delta = _naive(event) - _naive(now)
	return timedelta(0) <= delta <= timedelta(minutes=lead)


def _naive(value):
	value = get_datetime(value)
	return value.replace(tzinfo=None) if getattr(value, "tzinfo", None) else value


def _clock(value) -> str:
	return get_datetime(value).strftime("%H:%M")


def _punch_flags(employee: str, day) -> dict:
	from hrms_custom.api.attendance import today_punch_state

	state = today_punch_state(employee, day)
	return {"in": bool(state.get("first_in")), "out": bool(state.get("last_out"))}
