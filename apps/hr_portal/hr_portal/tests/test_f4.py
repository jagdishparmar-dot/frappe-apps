from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from hr_portal.lib.salary_structure import build_salary_components, compute_ctc_monthly
from hr_portal.permissions import payslip_has_permission
from hr_portal.services.payroll_service import (
	WORKING_DAYS_DEFAULT,
	compute_payable_days,
	compute_payslip_breakdown,
	export_bank_csv,
	run_payroll,
	upsert_salary_structure,
)


class TestF4SalaryStructure(IntegrationTestCase):
	def test_build_components_and_ctc(self):
		amounts = {
			"basic": 20000,
			"hra": 8000,
			"special_allowance": 5000,
			"other_earnings": 1000,
			"deductions": 2000,
		}
		components = build_salary_components(amounts)
		self.assertEqual(len(components), 5)
		self.assertEqual(compute_ctc_monthly(amounts), 32000)


class TestF4PayrollFlow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.commit()

	def setUp(self):
		self._created: list[tuple[str, str]] = []
		self.month = "2026-09"

		self.employee = frappe.get_doc(
			{
				"doctype": "HR Employee",
				"employee_code": "F4EMP",
				"employee_name": "F4 Employee",
				"email": "f4.emp@example.com",
				"status": "Active",
				"portal_role": "HR Employee",
				"employment_type": "Permanent",
				"attendance_policy": "gps_logged",
				"bank_account_number": "1234567890",
				"bank_ifsc": "HDFC0001234",
			}
		)
		self.employee.insert(ignore_permissions=True)
		self._created.append(("HR Employee", self.employee.name))

		structure_id = upsert_salary_structure(
			self.employee.name,
			"2026-01-01",
			{"basic": 20000, "hra": 8000, "special_allowance": 0, "other_earnings": 0, "deductions": 2000},
		)
		self._created.append(("HR Salary Structure", structure_id))

		for day in ("2026-09-01", "2026-09-02", "2026-09-03"):
			att = frappe.get_doc(
				{
					"doctype": "HR Attendance",
					"employee": self.employee.name,
					"date_iso": day,
					"status": "PRESENT",
				}
			)
			att.flags.ignore_permissions = True
			att.insert()
			self._created.append(("HR Attendance", att.name))

		frappe.db.commit()

	def tearDown(self):
		for slip in frappe.get_all("HR Payslip", filters={"employee": self.employee.name}, pluck="name"):
			frappe.delete_doc("HR Payslip", slip, force=1)
		for run in frappe.get_all("HR Payroll Run", filters={"month": self.month}, pluck="name"):
			frappe.delete_doc("HR Payroll Run", run, force=1)
		for doctype, name in reversed(self._created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=1)
		frappe.db.commit()

	def test_payable_days_and_proration(self):
		days = compute_payable_days(self.employee.name, self.month, WORKING_DAYS_DEFAULT)
		self.assertEqual(days["present_days"], 3)
		self.assertEqual(days["payable_days"], 3)
		self.assertAlmostEqual(days["ratio"], 3 / 22)

		structure = frappe.get_doc(
			"HR Salary Structure",
			frappe.get_all("HR Salary Structure", filters={"employee": self.employee.name}, pluck="name")[0],
		)
		breakdown = compute_payslip_breakdown(structure, self.employee.name, self.month)
		self.assertAlmostEqual(breakdown["gross"], 28000 * (3 / 22))
		self.assertAlmostEqual(breakdown["deductions_total"], 2000 * (3 / 22))
		self.assertAlmostEqual(breakdown["net_pay"], breakdown["gross"] - breakdown["deductions_total"])

	def test_run_payroll_and_bank_csv(self):
		run_id = run_payroll(self.month)
		self.assertTrue(frappe.db.exists("HR Payroll Run", run_id))
		self.assertEqual(frappe.db.get_value("HR Payroll Run", run_id, "status"), "Finalized")

		slips = frappe.get_all("HR Payslip", filters={"payroll_run": run_id})
		self.assertEqual(len(slips), 1)

		csv = export_bank_csv(run_id)
		self.assertIn("employeeCode,name,bankAccountNumber,bankIfsc,netPay,month", csv)
		self.assertIn("F4EMP", csv)
		self.assertIn("1234567890", csv)

		with self.assertRaises(Exception):
			run_payroll(self.month)


class TestF4PayslipPermissions(IntegrationTestCase):
	def test_employee_cannot_read_other_payslip(self):
		slip = frappe._dict({"employee": "EMP-A"})
		self.assertFalse(payslip_has_permission(slip, "read", "other.user@example.com"))
