from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from hr_portal.services.leave_service import (
	dates_in_range,
	day_count,
	ranges_overlap,
	sync_leave_request_to_attendance,
	validate_leave_application,
)
from hr_portal.services.shift_service import generate_rotational_roster, submit_shift_change_request


class TestF3LeaveLogic(IntegrationTestCase):
	def test_day_count_and_overlap(self):
		self.assertEqual(day_count("2026-07-28", "2026-07-30"), 3)
		self.assertTrue(ranges_overlap("2026-07-28", "2026-07-30", "2026-07-29", "2026-07-31"))
		self.assertFalse(ranges_overlap("2026-07-28", "2026-07-30", "2026-08-01", "2026-08-02"))
		self.assertEqual(len(dates_in_range("2026-07-28", "2026-07-29")), 2)


class TestF3LeaveFlow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.commit()

	def setUp(self):
		self._created: list[tuple[str, str]] = []
		self.leave_type = frappe.get_doc(
			{
				"doctype": "HR Leave Type",
				"leave_type_name": "F3 Casual",
				"code": "F3CL",
				"status": "Active",
				"paid": 1,
				"accrual_per_month": 2,
				"max_balance": 24,
			}
		)
		self.leave_type.insert(ignore_permissions=True)
		self._created.append(("HR Leave Type", self.leave_type.name))

		self.employee = frappe.get_doc(
			{
				"doctype": "HR Employee",
				"employee_code": "F3EMP",
				"employee_name": "F3 Employee",
				"email": "f3.emp@example.com",
				"status": "Active",
				"portal_role": "HR Employee",
				"attendance_policy": "gps_logged",
			}
		)
		self.employee.insert(ignore_permissions=True)
		self._created.append(("HR Employee", self.employee.name))

		self.balance = frappe.get_doc(
			{
				"doctype": "HR Leave Balance",
				"employee": self.employee.name,
				"leave_type": self.leave_type.name,
				"year": 2026,
				"balance": 5,
			}
		)
		self.balance.insert(ignore_permissions=True)
		self._created.append(("HR Leave Balance", self.balance.name))
		frappe.db.commit()

	def tearDown(self):
		for doctype in ("HR Attendance", "HR Leave Request", "HR Shift Assignment", "HR Shift Change Request"):
			for name in frappe.get_all(doctype, filters={"employee": self.employee.name}, pluck="name"):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, force=1)
		for doctype, name in reversed(self._created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=1)
		frappe.db.commit()

	def test_apply_leave_syncs_attendance_pending(self):
		validation = validate_leave_application(
			self.employee.name,
			self.leave_type.name,
			"2026-09-15",
			"2026-09-16",
		)
		self.assertTrue(validation["ok"])

		req = frappe.get_doc(
			{
				"doctype": "HR Leave Request",
				"employee": self.employee.name,
				"leave_type": self.leave_type.name,
				"from_date": "2026-09-15",
				"to_date": "2026-09-16",
				"days": 2,
				"status": "Pending",
			}
		)
		req.flags.ignore_permissions = True
		req.insert()
		sync_leave_request_to_attendance(req, self.leave_type.leave_type_name)

		rows = frappe.get_all(
			"HR Attendance",
			filters={"employee": self.employee.name, "leave_request": req.name},
			fields=["status", "date_iso"],
		)
		self.assertEqual(len(rows), 2)
		self.assertTrue(all(r.status == "LEAVE_PENDING" for r in rows))


class TestF3ShiftFlow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.commit()

	def setUp(self):
		self._created: list[tuple[str, str]] = []
		self.shift_a = frappe.get_doc(
			{
				"doctype": "HR Shift",
				"shift_name": "F3 A",
				"code": "F3A",
				"status": "Active",
				"start_time": "09:00",
				"end_time": "18:00",
			}
		)
		self.shift_a.insert(ignore_permissions=True)
		self._created.append(("HR Shift", self.shift_a.name))

		self.shift_b = frappe.get_doc(
			{
				"doctype": "HR Shift",
				"shift_name": "F3 B",
				"code": "F3B",
				"status": "Active",
				"start_time": "16:00",
				"end_time": "00:30",
				"crosses_midnight": 1,
			}
		)
		self.shift_b.insert(ignore_permissions=True)
		self._created.append(("HR Shift", self.shift_b.name))

		self.employee = frappe.get_doc(
			{
				"doctype": "HR Employee",
				"employee_code": "F3SHF",
				"employee_name": "F3 Shift Emp",
				"email": "f3.shift@example.com",
				"status": "Active",
				"portal_role": "HR Employee",
				"attendance_policy": "gps_logged",
				"default_shift": self.shift_a.name,
			}
		)
		self.employee.insert(ignore_permissions=True)
		self._created.append(("HR Employee", self.employee.name))
		frappe.db.commit()

	def tearDown(self):
		for doctype in ("HR Shift Assignment", "HR Shift Change Request"):
			for name in frappe.get_all(doctype, filters={"employee": self.employee.name}, pluck="name"):
				if frappe.db.exists(doctype, name):
					frappe.delete_doc(doctype, name, force=1)
		for doctype, name in reversed(self._created):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=1)
		frappe.db.commit()

	def test_generate_rotational_roster(self):
		created = generate_rotational_roster(
			self.employee.name,
			frappe.utils.today(),
			4,
			"F3A,F3B,OFF,F3A",
		)
		self.assertEqual(created, 3)
		count = frappe.db.count("HR Shift Assignment", {"employee": self.employee.name})
		self.assertEqual(count, 3)
