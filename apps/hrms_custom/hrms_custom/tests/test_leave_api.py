import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_years, getdate

from hrms_custom.api import leave
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

EMPLOYEE_USER = "leave.employee@example.com"
HR_USER = "leave.hr@example.com"


class TestLeaveApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Leave Emp", mobile="9000014000")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Leave HR", "send_welcome_email": 0}
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
		for name in frappe.get_all("Leave Application", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Leave Application", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Leave Allocation", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Leave Allocation", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear()
		frappe.db.set_value("Company", self.company, "holiday_list", None)
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_type(self, name, **kwargs):
		if frappe.db.exists("Leave Type", name):
			doc = frappe.get_doc("Leave Type", name)
			doc.update(kwargs)
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			return name
		frappe.get_doc({"doctype": "Leave Type", "leave_type_name": name, "company": self.company, **kwargs}).insert(
			ignore_permissions=True
		)
		frappe.db.commit()
		return name

	def allocate(self, leave_type, days, start="2026-01-01", end="2026-12-31"):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": leave_type,
				"from_date": start,
				"to_date": end,
				"allocated": days,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def test_employee_balance_and_apply(self):
		casual = self.make_type("Casual Leave")
		self.allocate(casual, 12)
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(leave.my_leave_balance, year=2026)
		self.assertEqual(status, 200, body)
		row = next(b for b in body["data"]["balances"] if b["name"] == casual)
		self.assertEqual(row["allocated"], 12)
		self.assertEqual(row["available"], 12)

		status, body = call(
			leave.apply_leave,
			leave_type=casual,
			from_date="2026-06-01",
			to_date="2026-06-03",
			reason="Family function",
		)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["total_days"], 3)
		self.assertEqual(body["data"]["status"], "Open")
		frappe.db.commit()

		row = next(b for b in call(leave.my_leave_balance, year=2026)[1]["data"]["balances"] if b["name"] == casual)
		self.assertEqual(row["pending"], 3)
		self.assertEqual(row["available"], 9)

	def test_holidays_are_skipped_unless_included(self):
		if frappe.db.exists("Holiday List", "Leave Holidays"):
			frappe.delete_doc("Holiday List", "Leave Holidays", force=True, ignore_permissions=True)
		holidays = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Leave Holidays",
				"company": self.company,
				"from_date": "2026-10-01",
				"to_date": "2026-10-31",
				"holidays": [{"holiday_date": "2026-10-02", "description": "Gandhi Jayanti", "weekly_off": 0}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Company", self.company, "holiday_list", holidays.name)
		casual = self.make_type("Holiday Casual", include_holiday=0)
		self.allocate(casual, 10)
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		preview = call(leave.preview_leave, leave_type=casual, from_date="2026-10-01", to_date="2026-10-03")[1]["data"]
		self.assertEqual(preview["total_days"], 2)
		self.assertIn("2026-10-02", preview["holidays_skipped"])

	def test_insufficient_balance_and_overlap(self):
		earned = self.make_type("Earned Leave")
		self.allocate(earned, 2)
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(
			call(leave.apply_leave, leave_type=earned, from_date="2026-07-01", to_date="2026-07-05")[0],
			400,
		)
		self.assertEqual(call(leave.apply_leave, leave_type=earned, from_date="2026-07-01", to_date="2026-07-01")[0], 200)
		frappe.db.commit()
		self.assertEqual(call(leave.apply_leave, leave_type=earned, from_date="2026-07-01", to_date="2026-07-01")[0], 400)

	def test_half_day_and_lwp_without_allocation(self):
		lwp = self.make_type("Leave Without Pay", is_lwp=1)
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(
			leave.apply_leave,
			leave_type=lwp,
			from_date="2026-08-10",
			to_date="2026-08-10",
			half_day=1,
		)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["total_days"], 0.5)
		row = next(b for b in call(leave.my_leave_balance, year=2026)[1]["data"]["balances"] if b["name"] == lwp)
		self.assertIsNone(row["available"])

	def test_cancel_and_hr_review(self):
		sick = self.make_type("Sick Leave")
		self.allocate(sick, 8)
		frappe.set_user(EMPLOYEE_USER)
		name = call(leave.apply_leave, leave_type=sick, from_date="2026-09-01", to_date="2026-09-02")[1]["data"]["name"]
		frappe.db.commit()
		self.assertEqual(call(leave.review_leave, application=name, status="Approved")[0], 403)

		self.assertEqual(call(leave.cancel_leave, application=name)[0], 200)
		frappe.db.commit()
		self.assertEqual(call(leave.my_leave_applications)[1]["data"]["applications"][0]["status"], "Cancelled")

		name = call(leave.apply_leave, leave_type=sick, from_date="2026-09-08", to_date="2026-09-09")[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(HR_USER)
		status, body = call(leave.review_leave, application=name, status="Approved")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Approved")
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		name = call(leave.apply_leave, leave_type=sick, from_date="2026-09-21", to_date="2026-09-21")[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(HR_USER)
		self.assertEqual(call(leave.review_leave, application=name, status="Rejected")[0], 400)
		status, body = call(leave.review_leave, application=name, status="Rejected", remarks="Plan coverage first")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Rejected")

	def test_joiner_cannot_apply(self):
		email = "leave.joiner@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Joiner", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		joiner = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Leave Joiner",
				"date_of_joining": add_years(getdate(), 0),
				"company": self.company,
				"status": "Inactive",
				"onboarding_status": "Invited",
				"user_id": email,
				"cell_number": "9000014001",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user(email)
		self.assertEqual(call(leave.my_leave_balance)[0], 403)
		frappe.set_user("Administrator")
		frappe.delete_doc("Employee", joiner.name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_invalid_year_and_empty_entries(self):
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(leave.my_leave_balance, year="abc")[0], 400)
		self.assertEqual(call(leave.apply_leave, leave_type="Casual Leave")[0], 400)
		self.assertEqual(call(leave.cancel_leave)[0], 400)
