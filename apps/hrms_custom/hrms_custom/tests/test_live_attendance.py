import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from hrms_custom.api.attendance import get_live_attendance
from hrms_custom.tests.utils import call, get_test_company, make_employee_user
from hrms_custom.utils.reports import attendance_summary_rows, parse_day

EMPLOYEE_USER = "live.employee@example.com"
HR_USER = "live.hr@example.com"


class TestLiveAttendance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		if not frappe.db.exists("Department", {"department_name": "Live Dash Dept", "company": cls.company}):
			cls.department = (
				frappe.get_doc(
					{"doctype": "Department", "department_name": "Live Dash Dept", "company": cls.company}
				)
				.insert(ignore_permissions=True)
				.name
			)
		else:
			cls.department = frappe.db.get_value(
				"Department", {"department_name": "Live Dash Dept", "company": cls.company}
			)
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Live Emp", mobile="9000016000")
		frappe.db.set_value("Employee", cls.employee, "department", cls.department)
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Live HR", "send_welcome_email": 0}
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
		self._ensure_leave()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Company", self.company, "holiday_list", None)

	def _ensure_shift(self):
		if frappe.db.exists("Shift Type", "Live Day"):
			doc = frappe.get_doc("Shift Type", "Live Day")
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
					"shift_name": "Live Day",
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
				"shift_type": "Live Day",
				"start_date": "2026-04-01",
				"end_date": "2026-04-30",
				"status": "Active",
			}
		).insert(ignore_permissions=True)

	def _ensure_holiday(self):
		if frappe.db.exists("Holiday List", "Live Holidays"):
			frappe.delete_doc("Holiday List", "Live Holidays", force=True, ignore_permissions=True)
		holidays = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Live Holidays",
				"company": self.company,
				"from_date": "2026-04-01",
				"to_date": "2026-04-30",
				"holidays": [{"holiday_date": "2026-04-05", "description": "Live Off", "weekly_off": 1}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Company", self.company, "holiday_list", holidays.name)

	def _ensure_leave(self):
		if not frappe.db.exists("Leave Type", "Live Casual"):
			frappe.get_doc(
				{"doctype": "Leave Type", "leave_type_name": "Live Casual", "company": self.company}
			).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": "Live Casual",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"allocated": 5,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": "Live Casual",
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
				"device_id": "live-test",
			}
		).insert(ignore_permissions=True)

	def _snapshot(self, date):
		frappe.set_user(HR_USER)
		status, body = call(get_live_attendance, date=date, employee=self.employee)
		self.assertEqual(status, 200, body)
		return body["data"]

	def test_employee_cannot_view_live_attendance(self):
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(get_live_attendance, date="2026-04-02")
		self.assertEqual(status, 403, body)
		self.assertIn("Only HR", body["message"])

	def test_invalid_date_is_rejected(self):
		frappe.set_user(HR_USER)
		self.assertEqual(call(get_live_attendance, date="2026-13-01")[0], 400)
		self.assertEqual(call(get_live_attendance, date="not-a-date")[0], 400)
		self.assertEqual(call(get_live_attendance, date="2026-04-31")[0], 400)
		self.assertRaises(frappe.ValidationError, parse_day, "2026-04-31")

	def test_counts_match_summary_and_statuses(self):
		self._punch("2026-04-02 09:40:00")
		self._punch("2026-04-02 18:00:00", "OUT")
		frappe.db.commit()

		late_day = self._snapshot("2026-04-02")
		self.assertEqual(late_day["date"], "2026-04-02")
		self.assertEqual(late_day["counts"], {"present": 1, "absent": 0, "late": 1, "half_day": 0, "on_leave": 0})
		self.assertEqual(late_day["employees"][0]["status"], "Late")
		self.assertEqual(late_day["employees"][0]["shift_type"], "Live Day")
		self.assertTrue(late_day["employees"][0]["in_time"])
		self.assertTrue(late_day["employees"][0]["out_time"])

		leave_day = self._snapshot("2026-04-03")
		self.assertEqual(leave_day["counts"], {"present": 0, "absent": 0, "late": 0, "half_day": 0, "on_leave": 1})
		self.assertEqual(leave_day["employees"][0]["status"], "On Leave")

		holiday = self._snapshot("2026-04-05")
		self.assertEqual(holiday["counts"], {"present": 0, "absent": 0, "late": 0, "half_day": 0, "on_leave": 0})
		self.assertEqual(holiday["employees"][0]["status"], "Holiday")

		absent = self._snapshot("2026-04-06")
		self.assertEqual(absent["counts"], {"present": 0, "absent": 1, "late": 0, "half_day": 0, "on_leave": 0})
		self.assertEqual(absent["employees"][0]["status"], "Absent")

		frappe.set_user("Administrator")
		summary = attendance_summary_rows(
			{"from_date": "2026-04-02", "to_date": "2026-04-02", "employee": self.employee}
		)
		self.assertEqual(summary[0]["present"], late_day["counts"]["present"])
		self.assertEqual(summary[0]["late"], late_day["counts"]["late"])
		self.assertEqual(summary[0]["absent"], late_day["counts"]["absent"])
		self.assertEqual(summary[0]["on_leave"], late_day["counts"]["on_leave"])

	def test_defaults_to_today(self):
		frappe.set_user(HR_USER)
		status, body = call(get_live_attendance, employee=self.employee)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["date"], getdate().isoformat())

	def test_page_and_sidebar(self):
		self.assertEqual(frappe.db.exists("Page", "live-attendance"), "live-attendance")
		labels = {row.label for row in frappe.get_doc("Workspace Sidebar", "HRMS").items}
		self.assertIn("Live Attendance", labels)
		page = frappe.get_doc("Page", "live-attendance")
		self.assertEqual(page.title, "Live Attendance")

	def test_desk_call_is_allowed_over_post(self):
		"""Desk frappe.call POSTs; a GET-only whitelist raises Frappe's Not Permitted."""
		allowed = frappe.allowed_http_methods_for_whitelisted_func[get_live_attendance]
		self.assertIn("GET", allowed)
		self.assertIn("POST", allowed)
