import frappe
from frappe.tests import IntegrationTestCase

from hrms_custom.api.attendance import my_attendance
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

EMPLOYEE_USER = "myatt.employee@example.com"
OTHER_USER = "myatt.other@example.com"


class TestMyAttendance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "MyAtt Emp", mobile="9000017000")
		cls.other = make_employee_user(OTHER_USER, cls.company, "MyAtt Other", mobile="9000017001")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._clear()
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def _clear(cls):
		for employee in (cls.employee, cls.other):
			for name in frappe.get_all("Employee Checkin", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Employee Checkin", name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Leave Application", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Leave Application", name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Leave Allocation", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Leave Allocation", name, force=True, ignore_permissions=True)
			for name in frappe.get_all("Shift Assignment", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear()
		frappe.db.set_value("Company", self.company, "holiday_list", None)
		self._ensure_shift()
		self._ensure_holiday()
		self._ensure_leave()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Company", self.company, "holiday_list", None)

	def _ensure_shift(self):
		if frappe.db.exists("Shift Type", "MyAtt Day"):
			doc = frappe.get_doc("Shift Type", "MyAtt Day")
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
					"shift_name": "MyAtt Day",
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
				"shift_type": "MyAtt Day",
				"start_date": "2026-04-01",
				"end_date": "2026-04-30",
				"status": "Active",
			}
		).insert(ignore_permissions=True)

	def _ensure_holiday(self):
		if frappe.db.exists("Holiday List", "MyAtt Holidays"):
			frappe.delete_doc("Holiday List", "MyAtt Holidays", force=True, ignore_permissions=True)
		holidays = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "MyAtt Holidays",
				"company": self.company,
				"from_date": "2026-04-01",
				"to_date": "2026-04-30",
				"holidays": [{"holiday_date": "2026-04-05", "description": "MyAtt Off", "weekly_off": 1}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Company", self.company, "holiday_list", holidays.name)

	def _ensure_leave(self):
		if not frappe.db.exists("Leave Type", "MyAtt Casual"):
			frappe.get_doc(
				{"doctype": "Leave Type", "leave_type_name": "MyAtt Casual", "company": self.company}
			).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": "MyAtt Casual",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"allocated": 5,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": "MyAtt Casual",
				"from_date": "2026-04-03",
				"to_date": "2026-04-03",
				"status": "Approved",
				"reason": "Personal",
				"remarks": "Covered",
			}
		).insert(ignore_permissions=True)

	def _punch(self, when, log_type="IN"):
		frappe.get_doc(
			{
				"doctype": "Employee Checkin",
				"employee": self.employee,
				"log_type": log_type,
				"time": when,
				"latitude": 23.0225,
				"longitude": 72.5714,
				"is_within_geofence": 1,
				"device_id": "myatt-test",
			}
		).insert(ignore_permissions=True)

	def test_month_statuses_times_and_hours(self):
		self._punch("2026-04-02 09:40:00")
		self._punch("2026-04-02 18:00:00", "OUT")
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		status, body = call(my_attendance, month="2026-04")
		self.assertEqual(status, 200, body)
		data = body["data"]
		self.assertEqual(data["month"], "2026-04")
		self.assertEqual(data["employee"], self.employee)

		late = data["days"]["2026-04-02"]
		self.assertEqual(late["status"], "Late")
		self.assertTrue(late["in_time"])
		self.assertTrue(late["out_time"])
		self.assertEqual(late["worked_minutes"], 500)
		self.assertEqual(late["worked_hours"], "8h 20m")
		self.assertEqual(late["shift_type"], "MyAtt Day")

		self.assertEqual(data["days"]["2026-04-03"]["status"], "On Leave")
		self.assertEqual(data["days"]["2026-04-05"]["status"], "Holiday")
		self.assertEqual(data["days"]["2026-04-06"]["status"], "Absent")
		self.assertGreaterEqual(data["counts"]["present"], 1)
		self.assertGreaterEqual(data["counts"]["late"], 1)
		self.assertGreaterEqual(data["counts"]["on_leave"], 1)
		self.assertGreaterEqual(data["counts"]["absent"], 1)

	def test_employee_only_sees_own_days(self):
		self._punch("2026-04-02 09:05:00")
		frappe.db.commit()
		frappe.set_user(OTHER_USER)
		status, body = call(my_attendance, month="2026-04")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["employee"], self.other)
		self.assertNotEqual(body["data"]["days"].get("2026-04-02", {}).get("status"), "Present")

	def test_invalid_month(self):
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(my_attendance, month="2026-13")[0], 400)
