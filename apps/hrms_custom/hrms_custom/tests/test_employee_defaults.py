import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, add_years, getdate

from hrms_custom.tests.utils import get_test_company


class TestEmployeeDefaults(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.shift = cls._ensure_shift("Defaults Day")
		cls.holidays = cls._ensure_holiday_list("Defaults Holidays")
		company = frappe.get_doc("Company", cls.company)
		company.default_shift = cls.shift
		company.holiday_list = cls.holidays
		company.default_week_off_weekdays = "Sunday"
		company.save(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value(
			"Company",
			cls.company,
			{"default_shift": None, "holiday_list": None},
			update_modified=False,
		)
		company = frappe.get_doc("Company", cls.company)
		company.default_week_off_weekdays = None
		company.save(ignore_permissions=True)
		super().tearDownClass()

	@classmethod
	def _ensure_shift(cls, name: str) -> str:
		if not frappe.db.exists("Shift Type", name):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"shift_name": name,
					"start_time": "09:00:00",
					"end_time": "18:00:00",
				}
			).insert(ignore_permissions=True)
		return name

	@classmethod
	def _ensure_holiday_list(cls, name: str) -> str:
		if frappe.db.exists("Holiday List", name):
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [{"holiday_date": "2026-01-26", "description": "Republic Day", "weekly_off": 0}],
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _cleanup_employee(self, name: str):
		for roster in frappe.get_all("Shift Roster", filters={"employee": name}, pluck="name"):
			frappe.delete_doc("Shift Roster", roster, force=True, ignore_permissions=True)
		for sa in frappe.get_all("Shift Assignment", filters={"employee": name}, pluck="name"):
			frappe.delete_doc("Shift Assignment", sa, force=True, ignore_permissions=True)
		if frappe.db.exists("Employee", name):
			frappe.delete_doc("Employee", name, force=True, ignore_permissions=True)

	def test_new_employee_gets_company_defaults(self):
		email = "defaults.emp@example.com"
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Defaults", "send_welcome_email": 0}
		).insert(ignore_permissions=True)

		join = getdate("2026-10-01")
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Defaults",
				"date_of_birth": add_years(join, -30),
				"date_of_joining": join,
				"company": self.company,
				"status": "Active",
				"user_id": email,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()

		self.assertEqual(frappe.db.get_value("Employee", emp.name, "holiday_list"), self.holidays)
		assignments = frappe.get_all(
			"Shift Assignment",
			filters={"employee": emp.name, "status": "Active"},
			fields=["shift_type", "start_date"],
		)
		self.assertEqual(len(assignments), 1)
		self.assertEqual(assignments[0].shift_type, self.shift)
		self.assertEqual(getdate(assignments[0].start_date), join)

		# First Sunday on or after join is 2026-10-04
		self.assertTrue(
			frappe.db.exists(
				"Shift Roster",
				{"employee": emp.name, "date": "2026-10-04", "is_week_off": 1},
			)
		)

		self._cleanup_employee(emp.name)
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
