import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_years, get_datetime, getdate

from hrms_custom.api import regularization
from hrms_custom.hrms_custom.report.punch_log.punch_log import execute as punch_log
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

EMPLOYEE_USER = "reg.employee@example.com"
HR_USER = "reg.hr@example.com"


class TestRegularizationApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, cls.company, "Reg Emp", mobile="9000016000")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Reg HR", "send_welcome_email": 0}
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
		for name in frappe.get_all("Attendance Regularization", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Attendance Regularization", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Employee Checkin", filters={"employee": cls.employee}, pluck="name"):
			frappe.delete_doc("Employee Checkin", name, force=True, ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self._clear()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_request_cancel_and_hr_approve_writes_checkins(self):
		day = "2026-02-10"
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(
			regularization.request_regularization,
			date=day,
			requested_check_in="09:05:00",
			requested_check_out="18:00:00",
			reason="Forgot to punch",
		)
		self.assertEqual(status, 200, body)
		name = body["data"]["name"]
		self.assertEqual(body["data"]["status"], "Open")
		frappe.db.commit()

		self.assertEqual(call(regularization.review_regularization, request=name, status="Approved")[0], 403)

		self.assertEqual(call(regularization.cancel_regularization, request=name)[0], 200)
		frappe.db.commit()
		self.assertEqual(call(regularization.my_regularizations)[1]["data"]["requests"][0]["status"], "Cancelled")

		name = call(
			regularization.request_regularization,
			date=day,
			requested_check_in="09:05:00",
			requested_check_out="18:00:00",
			reason="Forgot to punch",
		)[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(HR_USER)
		status, body = call(regularization.approve_regularization, request=name)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Approved")
		self.assertTrue(body["data"]["applied_in"])
		self.assertTrue(body["data"]["applied_out"])
		frappe.db.commit()

		inn = frappe.get_doc("Employee Checkin", body["data"]["applied_in"])
		out = frappe.get_doc("Employee Checkin", body["data"]["applied_out"])
		self.assertEqual(inn.log_type, "IN")
		self.assertEqual(get_datetime(inn.time).strftime("%H:%M:%S"), "09:05:00")
		self.assertEqual(inn.attendance_regularization, name)
		self.assertEqual(out.log_type, "OUT")
		self.assertEqual(get_datetime(out.time).strftime("%H:%M:%S"), "18:00:00")

		_, punches = punch_log({"from_date": day, "to_date": day, "employee": self.employee})
		self.assertEqual({p.log_type for p in punches}, {"IN", "OUT"})

	def test_approve_updates_existing_checkin(self):
		day = "2026-02-11"
		existing = frappe.get_doc(
			{
				"doctype": "Employee Checkin",
				"employee": self.employee,
				"log_type": "IN",
				"time": "2026-02-11 08:00:00",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user(EMPLOYEE_USER)
		name = call(
			regularization.request_regularization,
			date=day,
			requested_check_in="10:15:00",
			reason="Wrong punch time",
		)[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(HR_USER)
		status, body = call(regularization.review_regularization, request=name, status="Approved")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["applied_in"], existing.name)
		frappe.db.commit()
		self.assertEqual(get_datetime(frappe.get_doc("Employee Checkin", existing.name).time).strftime("%H:%M:%S"), "10:15:00")

	def test_reject_needs_remarks_and_second_open_is_blocked(self):
		day = "2026-02-12"
		frappe.set_user(EMPLOYEE_USER)
		name = call(
			regularization.request_regularization,
			date=day,
			requested_check_in="09:00:00",
			reason="Missed IN",
		)[1]["data"]["name"]
		frappe.db.commit()
		self.assertEqual(
			call(regularization.request_regularization, date=day, requested_check_out="18:00:00", reason="Again")[0],
			400,
		)
		frappe.set_user(HR_USER)
		self.assertEqual(call(regularization.review_regularization, request=name, status="Rejected")[0], 400)
		status, body = call(
			regularization.review_regularization,
			request=name,
			status="Rejected",
			remarks="Need manager confirmation",
		)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Rejected")
		self.assertFalse(frappe.get_all("Employee Checkin", filters={"employee": self.employee, "attendance_regularization": name}))

	def test_future_date_empty_payload_and_joiner(self):
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(regularization.request_regularization, date=str(add_days(getdate(), 1)), reason="Soon")[0], 400)
		self.assertEqual(call(regularization.request_regularization, date="2026-02-13")[0], 400)
		self.assertEqual(call(regularization.cancel_regularization)[0], 400)

		email = "reg.joiner@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Joiner", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		joiner = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Reg Joiner",
				"date_of_joining": add_years(getdate(), 0),
				"company": self.company,
				"status": "Inactive",
				"onboarding_status": "Invited",
				"user_id": email,
				"cell_number": "9000016001",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user(email)
		self.assertEqual(
			call(regularization.request_regularization, date="2026-02-13", requested_check_in="09:00:00", reason="Hi")[0],
			403,
		)
		frappe.set_user("Administrator")
		frappe.delete_doc("Employee", joiner.name, force=True, ignore_permissions=True)
		frappe.db.commit()
