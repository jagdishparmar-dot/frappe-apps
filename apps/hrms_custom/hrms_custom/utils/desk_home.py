"""Number-card helpers for the HRMS Desk workspace."""

import frappe

from hrms_custom.permissions import is_hr
from hrms_custom.utils.reports import live_attendance


def _today_counts() -> dict:
	cached = getattr(frappe.local, "_hrms_today_counts", None)
	if cached is not None:
		return cached
	if not is_hr():
		cached = {"present": 0, "late": 0, "absent": 0, "half_day": 0, "on_leave": 0}
	else:
		cached = live_attendance({}).get("counts") or {"present": 0, "late": 0, "absent": 0, "half_day": 0, "on_leave": 0}
	frappe.local._hrms_today_counts = cached
	return cached


def _metric(name: str) -> dict:
	return {"value": int(_today_counts().get(name) or 0)}


@frappe.whitelist()
def today_present(filters=None):
	return _metric("present")


@frappe.whitelist()
def today_late(filters=None):
	return _metric("late")


@frappe.whitelist()
def today_absent(filters=None):
	return _metric("absent")


@frappe.whitelist()
def today_on_leave(filters=None):
	return _metric("on_leave")
