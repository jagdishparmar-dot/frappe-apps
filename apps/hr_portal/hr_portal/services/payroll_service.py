from __future__ import annotations

import re

import frappe
from frappe import _

from hr_portal.lib.salary_structure import build_salary_components, compute_ctc_monthly, normalize_amounts_payload
from hr_portal.services.audit_service import write_audit_log

WORKING_DAYS_DEFAULT = 22
PRESENT_STATUSES = ("PRESENT", "LATE", "HALF_DAY")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def validate_month(month: str) -> str:
	month = (month or "").strip()
	if not MONTH_RE.match(month):
		frappe.throw(_("Month must be YYYY-MM"))
	return month


def is_payroll_eligible_employee(employee: dict) -> bool:
	if (employee.get("status") or "").lower() != "active":
		return False
	employment_type = employee.get("employment_type") or "Permanent"
	return employment_type == "Permanent"


def get_active_salary_structure(employee: str) -> frappe._dict | None:
	rows = frappe.get_all(
		"HR Salary Structure",
		filters={"employee": employee, "status": "Active"},
		fields=["name"],
		order_by="effective_from desc",
		limit=1,
	)
	if not rows:
		return None
	return frappe.get_doc("HR Salary Structure", rows[0].name)


def upsert_salary_structure(employee: str, effective_from: str, amounts: dict) -> str:
	if not frappe.db.exists("HR Employee", employee):
		frappe.throw(_("Employee not found"))

	normalized = normalize_amounts_payload(amounts)
	components = build_salary_components(normalized)
	ctc_monthly = compute_ctc_monthly(normalized)

	for row in frappe.get_all(
		"HR Salary Structure",
		filters={"employee": employee, "status": "Active"},
		pluck="name",
	):
		doc = frappe.get_doc("HR Salary Structure", row)
		doc.status = "Inactive"
		doc.flags.ignore_permissions = True
		doc.save()

	structure = frappe.get_doc(
		{
			"doctype": "HR Salary Structure",
			"employee": employee,
			"effective_from": effective_from,
			"status": "Active",
			"ctc_monthly": ctc_monthly,
			"components": components,
		}
	)
	structure.flags.ignore_permissions = True
	structure.insert()
	return structure.name


def compute_payable_days(employee: str, month: str, working_days: int = WORKING_DAYS_DEFAULT) -> dict:
	present_days = frappe.db.count(
		"HR Attendance",
		{
			"employee": employee,
			"status": ("in", PRESENT_STATUSES),
			"date_iso": ("like", f"{month}%"),
		},
	)
	leave_rows = frappe.get_all(
		"HR Leave Request",
		filters={"employee": employee, "status": "Approved", "from_date": ("like", f"{month}%")},
		fields=["days"],
	)
	leave_days = sum(int(row.days or 0) for row in leave_rows)
	payable_days = min(working_days, present_days + leave_days)
	ratio = (payable_days / working_days) if working_days > 0 else 0.0
	return {
		"working_days": working_days,
		"present_days": present_days,
		"leave_days": leave_days,
		"payable_days": payable_days,
		"ratio": ratio,
	}


def compute_payslip_breakdown(structure: frappe._dict, employee: str, month: str, working_days: int = WORKING_DAYS_DEFAULT) -> dict:
	days = compute_payable_days(employee, month, working_days)
	ratio = days["ratio"]

	earnings = sum(float(row.amount or 0) for row in structure.components if row.component_type == "earning")
	deductions = sum(float(row.amount or 0) for row in structure.components if row.component_type == "deduction")
	gross = earnings * ratio
	deductions_total = deductions * ratio
	net_pay = max(0.0, gross - deductions_total)

	lines = []
	for row in structure.components:
		amount = float(row.amount or 0) * ratio
		lines.append(
			{
				"component_key": row.component_key,
				"label": row.label,
				"amount": amount,
				"component_type": row.component_type,
			}
		)

	return {
		**days,
		"gross": gross,
		"deductions_total": deductions_total,
		"net_pay": net_pay,
		"lines": lines,
		"components": [
			{
				"key": row.component_key,
				"label": row.label,
				"amount": float(row.amount or 0),
				"type": row.component_type,
			}
			for row in structure.components
		],
	}


def run_payroll(month: str, working_days: int = WORKING_DAYS_DEFAULT) -> str:
	month = validate_month(month)

	existing_name = frappe.db.get_value("HR Payroll Run", {"month": month}, "name")
	if existing_name:
		status = frappe.db.get_value("HR Payroll Run", existing_name, "status")
		if status == "Finalized":
			frappe.throw(_("Payroll for this month is already finalized."))
		for slip in frappe.get_all("HR Payslip", filters={"payroll_run": existing_name}, pluck="name"):
			frappe.delete_doc("HR Payslip", slip, force=1)
		run = frappe.get_doc("HR Payroll Run", existing_name)
	else:
		run = frappe.get_doc(
			{
				"doctype": "HR Payroll Run",
				"month": month,
				"status": "Draft",
				"working_days": working_days,
			}
		)
		run.flags.ignore_permissions = True
		run.insert()

	employees = frappe.get_all(
		"HR Employee",
		filters={"status": "Active"},
		fields=["name", "status", "employment_type"],
	)
	total_net = 0.0
	count = 0

	for employee in employees:
		if not is_payroll_eligible_employee(employee):
			continue
		structure = get_active_salary_structure(employee.name)
		if not structure:
			continue

		breakdown = compute_payslip_breakdown(structure, employee.name, month, working_days)
		slip = frappe.get_doc(
			{
				"doctype": "HR Payslip",
				"payroll_run": run.name,
				"employee": employee.name,
				"month": month,
				"payable_days": breakdown["payable_days"],
				"working_days": breakdown["working_days"],
				"present_days": breakdown["present_days"],
				"leave_days": breakdown["leave_days"],
				"gross": breakdown["gross"],
				"deductions_total": breakdown["deductions_total"],
				"net_pay": breakdown["net_pay"],
				"lines": breakdown["lines"],
			}
		)
		slip.flags.ignore_permissions = True
		slip.insert()
		total_net += breakdown["net_pay"]
		count += 1

	run.employee_count = count
	run.total_net = total_net
	run.working_days = working_days
	run.status = "Finalized"
	run.flags.ignore_permissions = True
	run.save()

	write_audit_log(
		action="payroll.finalized",
		entity_type="payroll_run",
		entity_id=run.name,
		meta={"month": month, "count": count, "totalNet": total_net},
	)
	return run.name


def export_bank_csv(payroll_run_id: str) -> str:
	if not frappe.db.exists("HR Payroll Run", payroll_run_id):
		frappe.throw(_("Payroll run not found"))

	slips = frappe.get_all(
		"HR Payslip",
		filters={"payroll_run": payroll_run_id},
		fields=["employee", "net_pay", "month"],
		order_by="employee asc",
	)
	lines = ["employeeCode,name,bankAccountNumber,bankIfsc,netPay,month"]
	for slip in slips:
		emp = frappe.db.get_value(
			"HR Employee",
			slip.employee,
			["employee_code", "employee_name", "bank_account_number", "bank_ifsc"],
			as_dict=True,
		) or {}
		name = (emp.get("employee_name") or "").replace('"', '""')
		lines.append(
			",".join(
				[
					emp.get("employee_code") or "",
					f'"{name}"',
					emp.get("bank_account_number") or "",
					emp.get("bank_ifsc") or "",
					f"{float(slip.net_pay or 0):.2f}",
					slip.month or "",
				]
			)
		)

	write_audit_log(
		action="payroll.bank_csv_exported",
		entity_type="payroll_run",
		entity_id=payroll_run_id,
	)
	return "\n".join(lines)
