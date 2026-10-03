import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime

from hrms_custom.hrms_custom.report.attendance_summary.attendance_summary import execute as attendance_summary
from hrms_custom.hrms_custom.report.employee_date_wise_attendance.employee_date_wise_attendance import (
	execute as date_wise_attendance,
)
from hrms_custom.hrms_custom.report.employee_master.employee_master import execute as employee_master
from hrms_custom.hrms_custom.report.late_coming_and_early_going.late_coming_and_early_going import execute as late_early
from hrms_custom.hrms_custom.report.leave_balance.leave_balance import execute as leave_balance
from hrms_custom.hrms_custom.report.monthly_attendance_grid.monthly_attendance_grid import (
	execute as monthly_grid,
)
from hrms_custom.hrms_custom.report.onboarding_status.onboarding_status import execute as onboarding_status
from hrms_custom.hrms_custom.report.punch_log.punch_log import execute as punch_log
from hrms_custom.tests.utils import get_test_company, make_employee_user
from hrms_custom.utils.reports import parse_date_range

EMPLOYEE_USER = "reports.employee@example.com"
HR_USER = "reports.hr@example.com"


class TestReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		if not frappe.db.exists("Department", {"department_name": "Reports Dept", "company": cls.company}):
			cls.department = (
				frappe.get_doc(
					{"doctype": "Department", "department_name": "Reports Dept", "company": cls.company}
				)
				.insert(ignore_permissions=True)
				.name
			)
		else:
			cls.department = frappe.db.get_value("Department", {"department_name": "Reports Dept", "company": cls.company})
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Reports Emp", mobile="9000015000")
		frappe.db.set_value("Employee", cls.employee, "department", cls.department)
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Reports HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Executive")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._clear()
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def _clear(cls):
		for name in frappe.get_all("Employee Checkin", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Employee Checkin", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Leave Application", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Leave Application", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Leave Allocation", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Leave Allocation", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Shift Assignment", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear()
		frappe.db.set_value("Company", self.company, "holiday_list", None)
		self._ensure_shift()
		self._ensure_holiday()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Company", self.company, "holiday_list", None)

	def _ensure_shift(self):
		if frappe.db.exists("Shift Type", "Reports Day"):
			doc = frappe.get_doc("Shift Type", "Reports Day")
			doc.update(
				{
					"start_time": "09:00:00",
					"end_time": "18:00:00",
					"grace_minutes": 15,
					"is_active": 1,
					"minimum_hours_present": 0,
					"minimum_hours_half_day": 0,
					"allow_flexible_hours": 0,
					"early_exit_grace_minutes": 0,
				}
			)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"shift_name": "Reports Day",
					"company": self.company,
					"start_time": "09:00:00",
					"end_time": "18:00:00",
					"grace_minutes": 15,
				}
			).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": "Reports Day",
				"start_date": "2026-03-01",
				"end_date": "2026-03-31",
				"status": "Active",
			}
		).insert(ignore_permissions=True)

	def _ensure_holiday(self):
		if frappe.db.exists("Holiday List", "Reports Holidays"):
			frappe.delete_doc("Holiday List", "Reports Holidays", force=True, ignore_permissions=True)
		holidays = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Reports Holidays",
				"company": self.company,
				"from_date": "2026-03-01",
				"to_date": "2026-03-31",
				"holidays": [{"holiday_date": "2026-03-08", "description": "Reports Off", "weekly_off": 1}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Company", self.company, "holiday_list", holidays.name)

	def _punch(self, when, log_type="IN", **kwargs):
		frappe.get_doc(
			{
				"doctype": "Employee Checkin",
				"employee": self.employee,
				"log_type": log_type,
				"time": when,
				"latitude": 23.0225,
				"longitude": 72.5714,
				"is_within_geofence": kwargs.get("is_within_geofence", 1),
				"device_id": "reports-test",
			}
		).insert(ignore_permissions=True)

	def _row(self, rows, **matches):
		for row in rows:
			if all(row.get(key) == value for key, value in matches.items()):
				return row
		self.fail(f"no row matching {matches} in {rows}")

	def test_attendance_summary_and_late_early(self):
		self._punch("2026-03-02 09:05:00")
		self._punch("2026-03-02 18:00:00", "OUT")
		self._punch("2026-03-03 09:40:00")
		self._punch("2026-03-03 17:00:00", "OUT")
		frappe.get_doc(
			{
				"doctype": "Leave Type",
				"leave_type_name": "Reports Casual",
				"company": self.company,
			}
		).insert(ignore_permissions=True) if not frappe.db.exists("Leave Type", "Reports Casual") else None
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": "Reports Casual",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"allocated": 5,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": "Reports Casual",
				"from_date": "2026-03-04",
				"to_date": "2026-03-04",
				"status": "Approved",
				"reason": "Personal",
				"remarks": "Covered",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

		_, data = attendance_summary({"month": "2026-03", "employee": self.employee})
		row = self._row(data, employee=self.employee)
		self.assertEqual(row["present"], 2)
		self.assertEqual(row["late"], 1)
		self.assertEqual(row["on_leave"], 1)
		self.assertGreaterEqual(row["absent"], 1)

		_, punches = punch_log({"from_date": "2026-03-01", "to_date": "2026-03-31", "employee": self.employee})
		self.assertEqual(len(punches), 4)
		self.assertTrue(any(p.latitude and p.is_within_geofence for p in punches))

		_, late_rows = late_early({"from_date": "2026-03-01", "to_date": "2026-03-31", "employee": self.employee})
		late = self._row(late_rows, date="2026-03-03")
		self.assertEqual(late["late_minutes"], 25)
		self.assertEqual(late["early_minutes"], 60)
		self.assertFalse(any(r["date"] == "2026-03-02" for r in late_rows))

		_, days = date_wise_attendance({"month": "2026-03", "employee": self.employee})
		on_time = self._row(days, date="2026-03-02")
		self.assertEqual(on_time["status"], "Present")
		self.assertEqual(on_time["employee_name"], "Reports Emp")
		self.assertEqual(on_time["department"], self.department)
		self.assertEqual(get_datetime(on_time["in_time"]).hour, 9)
		self.assertEqual(get_datetime(on_time["out_time"]).hour, 18)
		late_day = self._row(days, date="2026-03-03")
		self.assertEqual(late_day["status"], "Late")
		self.assertEqual(get_datetime(late_day["in_time"]).minute, 40)
		self.assertEqual(self._row(days, date="2026-03-04")["status"], "On Leave")
		self.assertEqual(self._row(days, date="2026-03-08")["status"], "Holiday")
		self.assertGreaterEqual(sum(1 for row in days if row["status"] == "Absent"), 1)

		_, spanned = date_wise_attendance(
			{"from_date": "2026-03-02", "to_date": "2026-03-03", "employee": self.employee}
		)
		self.assertEqual({row["date"] for row in spanned}, {"2026-03-02", "2026-03-03"})

		_, balances = leave_balance({"year": 2026, "employee": self.employee, "leave_type": "Reports Casual"})
		balance = self._row(balances, leave_type="Reports Casual")
		self.assertEqual(balance["allocated"], 5)
		self.assertEqual(balance["taken"], 1)
		self.assertEqual(balance["available"], 4)

	def test_employee_master_and_onboarding_status(self):
		_, people = employee_master({"company": self.company, "employee": self.employee})
		row = self._row(people, name=self.employee)
		self.assertEqual(row["status"], "Active")
		self.assertEqual(row["department"], self.department)
		self.assertEqual(row.get("employee_type") or "Permanent", "Permanent")

		email = "reports.joiner@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Reports Joiner", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		if frappe.db.exists("Employee", {"user_id": email}):
			joiner = frappe.db.get_value("Employee", {"user_id": email}, "name")
		else:
			joiner = (
				frappe.get_doc(
					{
						"doctype": "Employee",
						"first_name": "Reports Joiner",
						"date_of_joining": "2026-03-01",
						"company": self.company,
						"status": "Inactive",
						"onboarding_status": "Invited",
						"user_id": email,
						"cell_number": "9000015001",
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		frappe.db.commit()
		_, rows = onboarding_status({"company": self.company, "onboarding_status": "Invited"})
		self.assertTrue(any(r["employee"] == joiner and r["onboarding_status"] == "Invited" for r in rows))

	def test_monthly_attendance_grid(self):
		self.assertRaises(frappe.ValidationError, monthly_grid, {})
		self.assertRaises(frappe.ValidationError, monthly_grid, {"month": ""})
		self.assertRaises(frappe.ValidationError, monthly_grid, {"month": "2026-3"})
		self.assertRaises(frappe.ValidationError, monthly_grid, {"month": "2026-13"})
		self.assertRaises(frappe.ValidationError, monthly_grid, {"month": "2026-03", "company": "No Such Co"})

		feb_columns, _feb_rows = monthly_grid({"month": "2026-02", "employee": self.employee})
		feb_days = [col for col in feb_columns if col["fieldname"].startswith("day_")]
		self.assertEqual([col["label"] for col in feb_days], [str(day) for day in range(1, 29)])

		shift = frappe.get_doc("Shift Type", "Reports Day")
		shift.minimum_hours_present = 8
		shift.minimum_hours_half_day = 4
		shift.save(ignore_permissions=True)
		self._punch("2026-03-02 09:05:00")
		self._punch("2026-03-02 18:00:00", "OUT")
		self._punch("2026-03-03 09:40:00")
		self._punch("2026-03-03 18:00:00", "OUT")
		self._punch("2026-03-05 09:05:00")
		self._punch("2026-03-05 14:00:00", "OUT")
		if not frappe.db.exists("Leave Type", "Reports Casual"):
			frappe.get_doc(
				{"doctype": "Leave Type", "leave_type_name": "Reports Casual", "company": self.company}
			).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": "Reports Casual",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"allocated": 5,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": "Reports Casual",
				"from_date": "2026-03-04",
				"to_date": "2026-03-04",
				"status": "Approved",
				"reason": "Personal",
				"remarks": "Covered",
			}
		).insert(ignore_permissions=True)

		created = []
		try:
			for first_name, joining, relieving, status in (
				("Grid Joiner", "2026-03-20", None, "Inactive"),
				("Grid Leaver", "2026-01-01", "2026-03-10", "Left"),
				("Grid Future", "2026-04-01", None, "Active"),
			):
				created.append(
					frappe.get_doc(
						{
							"doctype": "Employee",
							"first_name": first_name,
							"date_of_birth": "1990-01-15",
							"date_of_joining": joining,
							"relieving_date": relieving,
							"company": self.company,
							"department": self.department,
							"status": status,
						}
					)
					.insert(ignore_permissions=True)
					.name
				)
			frappe.db.commit()

			columns, rows = monthly_grid({"month": "2026-03", "company": self.company})
			day_columns = [col for col in columns if col["fieldname"].startswith("day_")]
			self.assertEqual(len(day_columns), 31)
			self.assertEqual(day_columns[0]["label"], "1")
			self.assertEqual(day_columns[-1]["fieldname"], "day_31")
			self.assertEqual(
				[col["fieldname"] for col in columns[:6]],
				["employee", "employee_name", "company", "department", "designation", "branch"],
			)
			self.assertEqual(
				[col["fieldname"] for col in columns[-4:]],
				["present", "absent", "leave", "half_day"],
			)

			row = self._row(rows, employee=self.employee)
			self.assertEqual(row["day_2"], "Present")
			self.assertEqual(row["day_3"], "Present")
			self.assertEqual(row["day_4"], "Leave")
			self.assertEqual(row["day_5"], "Half Day")
			self.assertEqual(row["day_6"], "Absent")
			self.assertEqual(row["day_8"], "Holiday")
			self.assertEqual(row["present"], 2)
			self.assertEqual(row["leave"], 1)
			self.assertEqual(row["half_day"], 1)
			self.assertEqual(row["absent"], 26)

			joiner = self._row(rows, employee=created[0])
			self.assertEqual(joiner["day_19"], "")
			self.assertEqual(joiner["day_20"], "Absent")
			self.assertEqual(joiner["present"], 0)
			self.assertEqual(joiner["absent"], 12)
			self.assertEqual(joiner["leave"], 0)
			self.assertEqual(joiner["half_day"], 0)

			leaver = self._row(rows, employee=created[1])
			self.assertEqual(leaver["day_8"], "Holiday")
			self.assertEqual(leaver["day_10"], "Absent")
			self.assertEqual(leaver["day_11"], "")
			self.assertEqual(leaver["absent"], 9)
			self.assertEqual(leaver["present"] + leaver["leave"] + leaver["half_day"], 0)

			self.assertFalse(any(item["employee"] == created[2] for item in rows))
		finally:
			frappe.set_user("Administrator")
			for name in created:
				if frappe.db.exists("Employee", name):
					frappe.db.set_value("Employee", name, "docstatus", 0)
					frappe.delete_doc("Employee", name, force=True, ignore_permissions=True)
			frappe.db.commit()

	def test_invalid_filters(self):
		self.assertRaises(frappe.ValidationError, parse_date_range, {"month": "2026-13"})
		self.assertRaises(frappe.ValidationError, attendance_summary, {"month": "2026-03", "company": "No Such Co"})
		self.assertRaises(frappe.ValidationError, parse_date_range, {"from_date": "2026-03-10", "to_date": "2026-03-01"})

	def test_workspace_lists_reports(self):
		labels = {row.label for row in frappe.get_doc("Workspace Sidebar", "HRMS").items}
		for expected in (
			"Attendance Summary",
			"Employee Date-wise Attendance",
			"Monthly Attendance Grid",
			"Punch Log",
			"Late Coming and Early Going",
			"Leave Balance",
			"Employee Master",
			"Onboarding Status",
			"Reports",
		):
			self.assertIn(expected, labels)
		for name in (
			"Attendance Summary",
			"Employee Date-wise Attendance",
			"Monthly Attendance Grid",
			"Punch Log",
			"Late Coming and Early Going",
			"Leave Balance",
			"Employee Master",
			"Onboarding Status",
		):
			self.assertEqual(frappe.db.exists("Report", name), name)
		self.assertEqual(frappe.db.get_value("Report", "Employee Date-wise Attendance", "prepared_report"), 1)

	def test_punch_times_are_datetime(self):
		self._punch("2026-03-02 09:05:00")
		frappe.db.commit()
		_, punches = punch_log({"from_date": "2026-03-02", "to_date": "2026-03-02", "employee": self.employee})
		self.assertEqual(get_datetime(punches[0].time).hour, 9)
