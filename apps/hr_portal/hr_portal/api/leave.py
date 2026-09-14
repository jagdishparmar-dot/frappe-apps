from __future__ import annotations

import frappe
from frappe import _

from hr_portal.api.serialize import staff_or_own
from hr_portal.constants import EMPLOYEE_WRITE_ROLES
from hr_portal.permissions import get_employee_name, is_staff
from hr_portal.services.leave_service import (
	dates_in_range,
	ensure_leave_balance,
	seed_leave_balances_for_employee,
	sync_leave_request_to_attendance,
	validate_leave_application,
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


def _map_leave_type(row: dict) -> dict:
	return {
		"id": row.name,
		"companyId": "default",
		"name": row.leave_type_name,
		"code": row.code,
		"paid": bool(row.paid),
		"accrualPerMonth": float(row.accrual_per_month or 0),
		"maxBalance": float(row.max_balance or 0),
		"carryForward": bool(row.carry_forward),
		"status": (row.status or "Active").lower(),
	}


def _map_balance(row: dict, type_name: str = "", type_code: str = "") -> dict:
	return {
		"id": row.name,
		"companyId": "default",
		"employeeId": row.employee,
		"leaveTypeId": row.leave_type,
		"leaveTypeName": type_name,
		"leaveTypeCode": type_code,
		"year": int(row.year or 0),
		"balance": float(row.balance or 0),
	}


def _map_request(row: dict, type_name: str = "") -> dict:
	return {
		"id": row.name,
		"companyId": "default",
		"employeeId": row.employee,
		"userId": row.user or "",
		"leaveTypeId": row.leave_type,
		"leaveTypeName": type_name,
		"fromDate": str(row.from_date),
		"toDate": str(row.to_date),
		"days": int(row.days or 0),
		"status": (row.status or "Pending").lower(),
		"approverUserId": row.reviewed_by or "",
		"note": row.note or "",
	}


@frappe.whitelist()
def get_snapshot(employee: str = "") -> dict:
	require_login()
	if employee:
		staff_or_own(employee)
		employee_name = employee
	elif is_staff():
		employee_name = get_employee_name() or ""
	else:
		employee_name = _own_or_staff()
	year = frappe.utils.now_datetime().year

	types = frappe.get_all(
		"HR Leave Type",
		filters={"status": "Active"},
		fields=[
			"name",
			"leave_type_name",
			"code",
			"paid",
			"accrual_per_month",
			"max_balance",
			"carry_forward",
			"status",
		],
		limit=50,
	)
	type_rows = [_map_leave_type(t) for t in types]
	type_by_id = {t["id"]: t for t in type_rows}

	balances = []
	if employee_name:
		for t in types:
			doc = ensure_leave_balance(
				employee_name,
				t.name,
				year,
				min(float(t.max_balance or 24), float(t.accrual_per_month or 1) * 12),
			)
			balances.append(
				_map_balance(doc.as_dict(), t.leave_type_name, t.code)
			)

	req_filters: dict = {"employee": employee_name} if employee_name else {}
	if is_staff() and not employee:
		req_filters = {}
		balance_rows = frappe.get_all(
			"HR Leave Balance",
			fields=["name", "employee", "leave_type", "year", "balance"],
			limit=2000,
		)
		balances = []
		for row in balance_rows:
			type_row = frappe.db.get_value(
				"HR Leave Type", row.leave_type, ["leave_type_name", "code"], as_dict=True
			) or {}
			balances.append(
				_map_balance(
					row,
					type_row.get("leave_type_name") or row.leave_type,
					type_row.get("code") or "",
				)
			)

	requests = frappe.get_all(
		"HR Leave Request",
		filters=req_filters,
		fields=[
			"name",
			"employee",
			"user",
			"leave_type",
			"from_date",
			"to_date",
			"days",
			"status",
			"reviewed_by",
			"note",
		],
		order_by="modified desc",
		limit=100,
	)

	holidays = frappe.get_all(
		"HR Holiday",
		fields=["name", "holiday_date", "holiday_name", "region"],
		order_by="holiday_date asc",
		limit=200,
	)

	payload = {
		"ok": True,
		"types": type_rows,
		"balances": balances,
		"holidays": [
			{
				"id": h.name,
				"companyId": "default",
				"date": str(h.holiday_date),
				"name": h.holiday_name,
				"region": h.region or "",
			}
			for h in holidays
		],
		"requests": [],
	}
	mapped_requests = []
	for r in requests:
		item = _map_request(r, type_by_id.get(r.leave_type, {}).get("name", r.leave_type))
		if is_staff():
			item["employeeName"] = frappe.db.get_value("HR Employee", r.employee, "employee_name") or r.employee
		mapped_requests.append(item)
	payload["requests"] = mapped_requests
	return payload


@frappe.whitelist()
def apply_leave(
	leave_type_id: str,
	from_date: str,
	to_date: str,
	note: str = "",
) -> dict:
	employee_name = _own_or_staff()
	validation = validate_leave_application(employee_name, leave_type_id, from_date, to_date)
	if not validation.get("ok"):
		frappe.throw(validation["error"])

	doc = frappe.get_doc(
		{
			"doctype": "HR Leave Request",
			"employee": employee_name,
			"user": frappe.session.user,
			"leave_type": leave_type_id,
			"from_date": from_date,
			"to_date": to_date,
			"days": validation["days"],
			"status": "Pending",
			"note": (note or "").strip(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()

	type_name = frappe.db.get_value("HR Leave Type", leave_type_id, "leave_type_name") or leave_type_id
	sync_leave_request_to_attendance(doc, type_name)
	return {"ok": True}


@frappe.whitelist()
def review_leave(leave_request_id: str, decision: str) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	decision_norm = (decision or "").strip().lower()
	if decision_norm not in ("approved", "rejected"):
		frappe.throw(_("Invalid decision"))

	doc = frappe.get_doc("HR Leave Request", leave_request_id)
	if doc.status != "Pending":
		frappe.throw(_("Request not reviewable"))

	doc.status = "Approved" if decision_norm == "approved" else "Rejected"
	doc.reviewed_by = frappe.session.user
	doc.reviewed_at = frappe.utils.now_datetime()

	if decision_norm == "approved":
		year = int(str(doc.from_date)[:4])
		balance = ensure_leave_balance(doc.employee, doc.leave_type, year)
		balance.balance = max(0, float(balance.balance or 0) - int(doc.days or 0))
		balance.flags.ignore_permissions = True
		balance.save()

	type_name = frappe.db.get_value("HR Leave Type", doc.leave_type, "leave_type_name") or doc.leave_type
	doc.flags.ignore_permissions = True
	doc.save()
	sync_leave_request_to_attendance(doc, type_name)
	return {"ok": True}


@frappe.whitelist()
def assign_balance(
	employee: str,
	leave_type_id: str,
	year: int,
	balance: float,
) -> dict:
	require_roles(*EMPLOYEE_WRITE_ROLES)
	doc = ensure_leave_balance(employee, leave_type_id, int(year), float(balance))
	doc.balance = float(balance)
	doc.flags.ignore_permissions = True
	doc.save()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def list_requests(status: str = "") -> dict:
	require_login()
	filters: dict = {}
	if status:
		filters["status"] = status.title()
	if not is_staff():
		name = get_employee_name()
		if not name:
			frappe.throw(_("No employee record found"))
		filters["employee"] = name
	elif get_employee_name() and not is_staff():
		filters["employee"] = get_employee_name()

	rows = frappe.get_all(
		"HR Leave Request",
		filters=filters,
		fields=[
			"name",
			"employee",
			"user",
			"leave_type",
			"from_date",
			"to_date",
			"days",
			"status",
			"reviewed_by",
			"note",
		],
		order_by="modified desc",
		limit=200,
	)
	requests = []
	for row in rows:
		emp_name = frappe.db.get_value("HR Employee", row.employee, "employee_name") or row.employee
		type_name = frappe.db.get_value("HR Leave Type", row.leave_type, "leave_type_name") or row.leave_type
		payload = _map_request(row, type_name)
		payload["employeeName"] = emp_name
		requests.append(payload)
	return {"ok": True, "requests": requests}
