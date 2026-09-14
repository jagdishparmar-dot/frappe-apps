from __future__ import annotations

import frappe
from frappe import _

from hr_portal.api.serialize import staff_or_own
from hr_portal.constants import EMPLOYEE_WRITE_ROLES
from hr_portal.permissions import get_employee_name, is_staff
from hr_portal.services.shift_service import (
	delete_assignment,
	generate_rotational_roster,
	get_employee_today_shifts,
	import_roster_csv,
	list_roster,
	list_shift_catalog,
	review_shift_change_request,
	save_assignment,
	submit_shift_change_request,
)
from hr_portal.utils import require_login, require_roles


def _own_or_staff(employee: str | None = None) -> str:
	require_login()
	if employee:
		staff_or_own(employee)
		return employee
	name = get_employee_name()
	if not name:
		frappe.throw(_("No employee record found"))
	return name


@frappe.whitelist()
def get_today_shifts() -> dict:
	employee = _own_or_staff()
	payload = get_employee_today_shifts(employee)
	return {"ok": True, **payload}


@frappe.whitelist()
def get_catalog() -> dict:
	require_login()
	return {"ok": True, "shifts": list_shift_catalog()}


@frappe.whitelist()
def list_assignments(from_date: str, to_date: str, employee: str = "") -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	return {
		"ok": True,
		"assignments": list_roster(from_date, to_date, employee),
	}


@frappe.whitelist()
def save_assignment_api(
	employee: str,
	assignment_date: str,
	shift: str,
	sequence: int = 1,
	site: str = "",
	note: str = "",
	name: str = "",
) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	assignment_id = save_assignment(
		employee,
		assignment_date,
		shift,
		int(sequence or 1),
		site,
		note,
		name or None,
	)
	return {"ok": True, "name": assignment_id}


@frappe.whitelist()
def delete_assignment_api(name: str) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	delete_assignment(name)
	return {"ok": True}


@frappe.whitelist()
def generate_roster(
	employee: str,
	start_date: str,
	days: int = 7,
	pattern: str = "",
) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	created = generate_rotational_roster(employee, start_date, int(days or 7), pattern)
	return {"ok": True, "created": created}


@frappe.whitelist()
def import_roster(csv_text: str) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	result = import_roster_csv(csv_text)
	if not result.get("ok"):
		frappe.throw(result.get("error") or "Import failed")
	return result


@frappe.whitelist()
def submit_change_request(
	date_iso: str,
	requested_shift_id: str,
	reason: str,
	sequence: int = 1,
) -> dict:
	employee = _own_or_staff()
	submit_shift_change_request(
		employee,
		frappe.session.user,
		date_iso,
		requested_shift_id,
		reason,
		int(sequence or 1),
	)
	return {"ok": True}


@frappe.whitelist()
def list_change_requests(employee: str = "") -> dict:
	require_login()
	filters: dict = {}
	if employee:
		staff_or_own(employee)
		filters["employee"] = employee
	elif not is_staff():
		name = get_employee_name()
		if not name:
			frappe.throw(_("No employee record found"))
		filters["employee"] = name

	rows = frappe.get_all(
		"HR Shift Change Request",
		filters=filters,
		fields=[
			"name",
			"employee",
			"user",
			"date_iso",
			"sequence",
			"current_shift",
			"requested_shift",
			"reason",
			"status",
			"review_note",
			"reviewed_by",
			"reviewed_at",
		],
		order_by="modified desc",
		limit=100,
	)
	requests = []
	for row in rows:
		emp_name = frappe.db.get_value("HR Employee", row.employee, "employee_name") or row.employee
		cur = frappe.db.get_value("HR Shift", row.current_shift, ["shift_name", "code"], as_dict=True) if row.current_shift else None
		req = frappe.db.get_value("HR Shift", row.requested_shift, ["shift_name", "code"], as_dict=True) or {}
		requests.append(
			{
				"id": row.name,
				"employeeId": row.employee,
				"employeeName": emp_name,
				"userId": row.user or "",
				"dateIso": str(row.date_iso),
				"sequence": int(row.sequence or 1),
				"currentShiftId": row.current_shift or "",
				"currentShiftName": cur.shift_name if cur else "",
				"currentShiftCode": cur.code if cur else "",
				"requestedShiftId": row.requested_shift,
				"requestedShiftName": req.get("shift_name") or row.requested_shift,
				"requestedShiftCode": req.get("code") or "",
				"reason": row.reason or "",
				"status": (row.status or "Pending").lower(),
				"reviewNote": row.review_note or "",
			}
		)
	return {"ok": True, "requests": requests}


@frappe.whitelist()
def review_change_request(
	request_id: str,
	decision: str,
	review_note: str = "",
) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	decision_norm = (decision or "").strip().lower()
	if decision_norm not in ("approved", "rejected"):
		frappe.throw(_("Invalid decision"))
	review_shift_change_request(request_id, decision_norm, review_note)
	return {"ok": True}
