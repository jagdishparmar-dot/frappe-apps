from __future__ import annotations

import frappe
from frappe import _

from hr_portal.constants import PAYROLL_ADMIN_ROLES
from hr_portal.lib.salary_structure import salary_amounts_from_components
from hr_portal.permissions import get_employee_name
from hr_portal.services.payroll_service import (
	export_bank_csv,
	get_active_salary_structure,
	run_payroll,
	upsert_salary_structure,
	validate_month,
)
from hr_portal.utils import require_login, require_roles


def _require_payroll_admin() -> None:
	require_roles(*PAYROLL_ADMIN_ROLES)


def _map_structure(doc) -> dict | None:
	if not doc:
		return None
	amounts = salary_amounts_from_components(doc.components)
	return {
		"id": doc.name,
		"companyId": "default",
		"employeeId": doc.employee,
		"effectiveFrom": str(doc.effective_from),
		"basic": amounts["basic"],
		"hra": amounts["hra"],
		"specialAllowance": amounts["special_allowance"],
		"otherEarnings": amounts["other_earnings"],
		"deductions": amounts["deductions"],
		"ctcMonthly": float(doc.ctc_monthly or 0),
		"status": (doc.status or "Active").lower(),
		"components": [
			{
				"key": row.component_key,
				"label": row.label,
				"amount": float(row.amount or 0),
				"type": row.component_type,
			}
			for row in doc.components
		],
	}


def _map_run(row: dict) -> dict:
	return {
		"id": row.name,
		"companyId": "default",
		"month": row.month,
		"status": (row.status or "Draft").lower(),
		"totals": {
			"employees": int(row.employee_count or 0),
			"totalNet": float(row.total_net or 0),
			"workingDays": int(row.working_days or 0),
		},
		"notes": row.notes or "",
	}


def _map_payslip(row: dict, employee_name: str = "", employee_code: str = "") -> dict:
	return {
		"id": row.name,
		"companyId": "default",
		"payrollRunId": row.payroll_run,
		"employeeId": row.employee,
		"employeeName": employee_name,
		"employeeCode": employee_code,
		"month": row.month,
		"netPay": float(row.net_pay or 0),
		"breakdown": {
			"payableDays": float(row.payable_days or 0),
			"workingDays": int(row.working_days or 0),
			"presentDays": int(row.present_days or 0),
			"leaveDays": int(row.leave_days or 0),
			"gross": float(row.gross or 0),
			"deductions": float(row.deductions_total or 0),
			"netPay": float(row.net_pay or 0),
		},
	}


@frappe.whitelist()
def get_salary_structure(employee: str) -> dict | None:
	_require_payroll_admin()
	if not employee:
		frappe.throw(_("Employee is required"))
	return _map_structure(get_active_salary_structure(employee))


@frappe.whitelist()
def save_salary_structure(
	employee: str,
	effective_from: str,
	basic: float = 0,
	hra: float = 0,
	special_allowance: float = 0,
	other_earnings: float = 0,
	deductions: float = 0,
) -> dict:
	_require_payroll_admin()
	if not employee or not effective_from:
		frappe.throw(_("Employee and effective from date are required"))
	name = upsert_salary_structure(
		employee,
		effective_from,
		{
			"basic": basic,
			"hra": hra,
			"special_allowance": special_allowance,
			"other_earnings": other_earnings,
			"deductions": deductions,
		},
	)
	return {"ok": True, "id": name}


@frappe.whitelist()
def run_payroll_action(month: str) -> dict:
	_require_payroll_admin()
	run_id = run_payroll(validate_month(month))
	return {"ok": True, "payrollRunId": run_id}


@frappe.whitelist()
def list_payroll_runs() -> list[dict]:
	_require_payroll_admin()
	rows = frappe.get_all(
		"HR Payroll Run",
		fields=["name", "month", "status", "employee_count", "total_net", "working_days", "notes"],
		order_by="month desc",
		limit=24,
	)
	return [_map_run(row) for row in rows]


@frappe.whitelist()
def list_payslips(payroll_run_id: str) -> list[dict]:
	require_login()
	if not payroll_run_id:
		frappe.throw(_("Payroll run is required"))

	roles = set(frappe.get_roles())
	is_admin = bool(roles.intersection(PAYROLL_ADMIN_ROLES)) or frappe.session.user == "Administrator"
	own = get_employee_name()

	rows = frappe.get_all(
		"HR Payslip",
		filters={"payroll_run": payroll_run_id},
		fields=[
			"name",
			"payroll_run",
			"employee",
			"month",
			"net_pay",
			"payable_days",
			"working_days",
			"present_days",
			"leave_days",
			"gross",
			"deductions_total",
		],
		order_by="employee asc",
		limit=500,
	)

	if not is_admin:
		if not own:
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		rows = [row for row in rows if row.employee == own]

	result = []
	for row in rows:
		emp = frappe.db.get_value(
			"HR Employee",
			row.employee,
			["employee_name", "employee_code"],
			as_dict=True,
		) or {}
		result.append(
			_map_payslip(
				row,
				employee_name=emp.get("employee_name") or "",
				employee_code=emp.get("employee_code") or "",
			)
		)
	return result


@frappe.whitelist()
def get_payslip(payslip_id: str) -> dict:
	require_login()
	if not payslip_id or not frappe.db.exists("HR Payslip", payslip_id):
		frappe.throw(_("Payslip not found"))

	slip = frappe.get_doc("HR Payslip", payslip_id)
	roles = set(frappe.get_roles())
	is_admin = bool(roles.intersection(PAYROLL_ADMIN_ROLES)) or frappe.session.user == "Administrator"
	own = get_employee_name()
	if not is_admin and slip.employee != own:
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	emp = frappe.db.get_value(
		"HR Employee",
		slip.employee,
		["employee_name", "employee_code", "department", "designation"],
		as_dict=True,
	) or {}
	mapped = _map_payslip(
		slip.as_dict(),
		employee_name=emp.get("employee_name") or "",
		employee_code=emp.get("employee_code") or "",
	)
	mapped["breakdown"]["components"] = [
		{
			"key": line.component_key,
			"label": line.label,
			"amount": float(line.amount or 0),
			"type": line.component_type,
		}
		for line in slip.lines
	]
	mapped["employee"] = {
		"name": emp.get("employee_name") or "",
		"code": emp.get("employee_code") or "",
		"department": emp.get("department") or "",
		"designation": emp.get("designation") or "",
	}
	return mapped


@frappe.whitelist()
def export_bank_csv_action(payroll_run_id: str) -> dict:
	_require_payroll_admin()
	csv = export_bank_csv(payroll_run_id)
	return {"ok": True, "csv": csv}


@frappe.whitelist()
def list_my_payslips() -> list[dict]:
	require_login()
	own = get_employee_name()
	if not own:
		frappe.throw(_("No employee record found"))

	rows = frappe.get_all(
		"HR Payslip",
		filters={"employee": own},
		fields=[
			"name",
			"payroll_run",
			"employee",
			"month",
			"net_pay",
			"payable_days",
			"working_days",
			"present_days",
			"leave_days",
			"gross",
			"deductions_total",
		],
		order_by="month desc",
		limit=24,
	)
	emp = frappe.db.get_value("HR Employee", own, ["employee_name", "employee_code"], as_dict=True) or {}
	return [
		_map_payslip(
			row,
			employee_name=emp.get("employee_name") or "",
			employee_code=emp.get("employee_code") or "",
		)
		for row in rows
	]
