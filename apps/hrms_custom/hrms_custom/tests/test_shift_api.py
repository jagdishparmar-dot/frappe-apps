import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_years, getdate

from hrms_custom.api import shift
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

EMPLOYEE_USER = "shift.employee@example.com"
HR_USER = "shift.hr@example.com"


class TestShiftApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Shift", mobile="9000012000")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Shift HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Executive")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Shift Assignment", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Shift Assignment", filters={"employee": self.employee}, pluck="name"):
			frappe.delete_doc("Shift Assignment", name, force=True, ignore_permissions=True)
		frappe.db.set_value("Company", self.company, "holiday_list", None)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_shift(self, name, start="09:00:00", end="18:00:00", **kwargs):
		if frappe.db.exists("Shift Type", name):
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"shift_name": name,
				"start_time": start,
				"end_time": end,
				"company": self.company,
				**kwargs,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def assign(self, shift_type, start, end=None):
		doc = frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": self.employee,
				"shift_type": shift_type,
				"start_date": start,
				"end_date": end,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def make_holidays(self, name, holidays):
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"company": self.company,
				"from_date": "2026-10-01",
				"to_date": "2026-10-31",
				"holidays": [{"holiday_date": d, "description": desc, "weekly_off": weekly} for d, desc, weekly in holidays],
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def test_hr_creates_shift_type_employee_cannot(self):
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(shift.create_shift_type, shift_name="Night", start_time="22:00:00", end_time="06:00:00")[0], 403)

		frappe.set_user("Administrator")
		if frappe.db.exists("Shift Type", "Night Test"):
			frappe.delete_doc("Shift Type", "Night Test", force=True, ignore_permissions=True)
			frappe.db.commit()
		frappe.set_user(HR_USER)
		status, body = call(
			shift.create_shift_type,
			shift_name="Night Test",
			start_time="22:00:00",
			end_time="06:00:00",
			grace_minutes=10,
		)
		self.assertEqual(status, 200, body)
		self.assertTrue(body["data"]["is_overnight"])
		self.assertEqual(body["data"]["start_time"], "22:00:00")
		self.assertEqual(body["data"]["grace_minutes"], 10)
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		listed = call(shift.list_shift_types)[1]["data"]["shift_types"]
		self.assertTrue(any(s["name"] == "Night Test" for s in listed))

	def test_calendar_includes_assignment_and_overlays_company_holiday(self):
		morning = self.make_shift("Morning Cal", location=None, color="#112233")
		self.assign(morning, "2026-10-01", "2026-10-31")
		holidays = self.make_holidays(
			"Oct 2026",
			[("2026-10-02", "Gandhi Jayanti", 0), ("2026-10-04", "Sunday", 1)],
		)
		frappe.db.set_value("Company", self.company, "holiday_list", holidays)
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		status, body = call(shift.my_shift_calendar, month="2026-10")
		self.assertEqual(status, 200, body)
		days = body["data"]["days"]
		self.assertEqual(body["data"]["month"], "2026-10")
		self.assertEqual(days["2026-10-01"]["shift"]["name"], "Morning Cal")
		self.assertFalse(days["2026-10-01"]["is_holiday"])
		self.assertTrue(days["2026-10-02"]["is_holiday"])
		self.assertEqual(days["2026-10-02"]["holiday"]["description"], "Gandhi Jayanti")
		self.assertEqual(days["2026-10-02"]["shift"]["name"], "Morning Cal")
		self.assertTrue(days["2026-10-04"]["holiday"]["weekly_off"])

	def test_shift_holiday_list_also_marks_days(self):
		offs = self.make_holidays("Night Offs", [("2026-10-07", "Night weekly off", 1)])
		night = self.make_shift("Night Cal", start="22:00:00", end="06:00:00", holiday_list=offs)
		self.assign(night, "2026-10-01", "2026-10-15")
		frappe.set_user(EMPLOYEE_USER)
		days = call(shift.my_shift_calendar, month="2026-10")[1]["data"]["days"]
		self.assertTrue(days["2026-10-07"]["is_holiday"])
		self.assertEqual(days["2026-10-07"]["holiday"]["description"], "Night weekly off")
		self.assertNotIn("2026-10-20", days)

	def test_overlapping_assignment_is_rejected(self):
		shift_name = self.make_shift("Overlap")
		self.assign(shift_name, "2026-10-01", "2026-10-15")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Shift Assignment",
					"employee": self.employee,
					"shift_type": shift_name,
					"start_date": "2026-10-10",
					"end_date": "2026-10-20",
					"status": "Active",
				}
			).insert(ignore_permissions=True)

	def test_invalid_month_and_empty_calendar(self):
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(shift.my_shift_calendar, month="2026-13")[0], 400)
		status, body = call(shift.my_shift_calendar, month="2026-11")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["days"], {})

	def test_joiner_cannot_read_calendar(self):
		email = "shift.joiner@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Joiner", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		joiner = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Joiner",
				"date_of_joining": add_years(getdate(), 0),
				"company": self.company,
				"status": "Inactive",
				"onboarding_status": "Invited",
				"user_id": email,
				"cell_number": "9000012001",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user(email)
		self.assertEqual(call(shift.my_shift_calendar, month="2026-10")[0], 403)
		frappe.set_user("Administrator")
		frappe.delete_doc("Employee", joiner.name, force=True, ignore_permissions=True)
		frappe.db.commit()
