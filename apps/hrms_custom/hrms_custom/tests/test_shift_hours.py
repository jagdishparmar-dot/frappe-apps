import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime

from hrms_custom.api import shift as shift_api
from hrms_custom.tests.utils import call, get_test_company, make_employee_user
from hrms_custom.utils.reports import employee_date_attendance_rows, employee_month_attendance, late_early_rows
from hrms_custom.utils.shifts import shift_duration_hours

EMPLOYEE_USER = "hours.employee@example.com"
HR_USER = "hours.hr@example.com"


class TestShiftHours(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Hours Emp", mobile="9000018000")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Hours HR", "send_welcome_email": 0}
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
		for name in frappe.get_all("Shift Assignment", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear()
		frappe.db.commit()

	def _shift(self, name, **kwargs):
		if frappe.db.exists("Shift Type", name):
			doc = frappe.get_doc("Shift Type", name)
			doc.update({"company": self.company, "is_active": 1, **kwargs})
			doc.save(ignore_permissions=True)
			return doc.name
		return (
			frappe.get_doc({"doctype": "Shift Type", "shift_name": name, "company": self.company, **kwargs})
			.insert(ignore_permissions=True)
			.name
		)

	def _assign(self, shift_type, start="2026-04-01", end="2026-04-30"):
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": shift_type,
				"start_date": start,
				"end_date": end,
				"status": "Active",
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
				"device_id": "hours-test",
			}
		).insert(ignore_permissions=True)

	def _day(self, date):
		rows = employee_date_attendance_rows({"from_date": date, "to_date": date, "employee": self.employee})
		self.assertEqual(len(rows), 1, rows)
		return rows[0]

	def test_duration_and_overnight_flag(self):
		self.assertEqual(shift_duration_hours("09:00:00", "18:00:00"), 9)
		self.assertEqual(shift_duration_hours("16:00:00", "02:00:00"), 10)
		name = self._shift("Hours Night Flag", start_time="16:00:00", end_time="02:00:00", working_hours=0)
		doc = frappe.get_doc("Shift Type", name)
		self.assertEqual(int(doc.is_overnight), 1)
		self.assertEqual(float(doc.working_hours), 10)

	def test_half_day_cannot_exceed_present(self):
		with self.assertRaises(frappe.ValidationError):
			self._shift(
				"Hours Bad Thresholds",
				start_time="09:00:00",
				end_time="18:00:00",
				minimum_hours_present=4,
				minimum_hours_half_day=5,
			)

	def test_present_half_day_and_short_hours(self):
		self._shift(
			"Hours Flex Day",
			start_time="09:00:00",
			end_time="18:00:00",
			grace_minutes=15,
			working_hours=9,
			minimum_hours_present=8,
			minimum_hours_half_day=4,
		)
		self._assign("Hours Flex Day")
		self._punch("2026-04-02 09:00:00")
		self._punch("2026-04-02 18:00:00", "OUT")
		self._punch("2026-04-03 09:00:00")
		self._punch("2026-04-03 13:00:00", "OUT")
		self._punch("2026-04-06 09:00:00")
		self._punch("2026-04-06 11:00:00", "OUT")
		frappe.db.commit()

		self.assertEqual(self._day("2026-04-02")["status"], "Present")
		self.assertEqual(self._day("2026-04-03")["status"], "Half Day")
		self.assertEqual(self._day("2026-04-03")["worked_minutes"], 240)
		self.assertEqual(self._day("2026-04-06")["status"], "Absent")

		month = employee_month_attendance(self.employee, "2026-04")
		self.assertEqual(month["days"]["2026-04-03"]["status"], "Half Day")
		self.assertGreaterEqual(month["counts"]["half_day"], 1)
		self.assertGreaterEqual(month["counts"]["present"], 1)

	def test_late_status_when_hours_are_met(self):
		self._shift(
			"Hours Late Day",
			start_time="09:00:00",
			end_time="18:00:00",
			grace_minutes=15,
			minimum_hours_present=8,
			minimum_hours_half_day=4,
		)
		self._assign("Hours Late Day")
		self._punch("2026-04-02 09:40:00")
		self._punch("2026-04-02 18:00:00", "OUT")
		frappe.db.commit()
		row = self._day("2026-04-02")
		self.assertEqual(row["status"], "Late")
		self.assertEqual(row["is_late"], 1)

	def test_flexible_hours_keeps_present_when_late(self):
		self._shift(
			"Hours Flexible",
			start_time="09:00:00",
			end_time="18:00:00",
			grace_minutes=15,
			allow_flexible_hours=1,
			minimum_hours_present=8,
			minimum_hours_half_day=4,
		)
		self._assign("Hours Flexible")
		self._punch("2026-04-02 10:00:00")
		self._punch("2026-04-02 18:30:00", "OUT")
		frappe.db.commit()
		row = self._day("2026-04-02")
		self.assertEqual(row["status"], "Present")
		self.assertEqual(row["is_late"], 1)
		late = late_early_rows({"from_date": "2026-04-02", "to_date": "2026-04-02", "employee": self.employee})
		self.assertEqual(late[0]["late_minutes"], 45)

	def test_early_exit_grace_skips_early_going(self):
		self._shift(
			"Hours Early Grace",
			start_time="09:00:00",
			end_time="18:00:00",
			grace_minutes=15,
			early_exit_grace_minutes=10,
		)
		self._assign("Hours Early Grace")
		self._punch("2026-04-02 09:00:00")
		self._punch("2026-04-02 17:55:00", "OUT")
		frappe.db.commit()
		self.assertEqual(
			late_early_rows({"from_date": "2026-04-02", "to_date": "2026-04-02", "employee": self.employee}),
			[],
		)

	def test_overnight_punches_belong_to_shift_start_date(self):
		self._shift(
			"Hours Overnight",
			start_time="16:00:00",
			end_time="02:00:00",
			grace_minutes=15,
			minimum_hours_present=8,
			minimum_hours_half_day=4,
		)
		self._assign("Hours Overnight")
		self._punch("2026-04-01 16:05:00")
		self._punch("2026-04-02 02:00:00", "OUT")
		frappe.db.commit()

		start_day = self._day("2026-04-01")
		next_day = self._day("2026-04-02")
		self.assertEqual(start_day["status"], "Present")
		self.assertEqual(get_datetime(start_day["in_time"]).hour, 16)
		self.assertEqual(get_datetime(start_day["out_time"]).day, 2)
		self.assertEqual(start_day["worked_minutes"], 595)
		self.assertNotEqual(next_day["status"], "Present")
		self.assertIsNone(next_day["in_time"])

		late = late_early_rows({"from_date": "2026-04-01", "to_date": "2026-04-02", "employee": self.employee})
		self.assertFalse(any(row["date"] == "2026-04-02" for row in late))

	def test_create_shift_type_returns_hour_fields(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("Shift Type", "Hours API Night"):
			frappe.delete_doc("Shift Type", "Hours API Night", force=True, ignore_permissions=True)
			frappe.db.commit()
		frappe.set_user(HR_USER)
		status, body = call(
			shift_api.create_shift_type,
			shift_name="Hours API Night",
			start_time="16:00:00",
			end_time="02:00:00",
			grace_minutes=10,
			early_exit_grace_minutes=5,
			working_hours=10,
			minimum_hours_present=8,
			minimum_hours_half_day=4,
			allow_flexible_hours=1,
		)
		self.assertEqual(status, 200, body)
		data = body["data"]
		self.assertTrue(data["is_overnight"])
		self.assertEqual(data["working_hours"], 10)
		self.assertEqual(data["minimum_hours_present"], 8)
		self.assertEqual(data["minimum_hours_half_day"], 4)
		self.assertEqual(data["early_exit_grace_minutes"], 5)
		self.assertEqual(data["allow_flexible_hours"], 1)
		frappe.db.commit()
