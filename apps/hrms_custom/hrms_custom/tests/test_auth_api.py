from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password, update_password

from hrms_custom.api import auth
from hrms_custom.api.profile import get_my_profile
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

USER = "otp.tester@example.com"
MOBILE = "+91 98765 43210"
PASSWORD = "ClockMe-Shift-2026!"


class TestOtpAuth(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.employee = make_employee_user(USER, get_test_company(), "Otp", mobile=MOBILE)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Guest")
		self.sent = []
		self._real_deliver = auth._deliver
		patcher = patch.object(auth, "_deliver", side_effect=lambda ident, otp, exp: self.sent.append(otp))
		patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")

	def request(self, identifier):
		status, body = call(auth.request_otp, mobile_or_email=identifier)
		self.assertEqual(status, 200, body)
		return self.sent[-1] if self.sent else None

	def test_login_with_email(self):
		otp = self.request(USER.upper())
		status, body = call(auth.verify_otp, mobile_or_email=USER, otp=otp)

		self.assertEqual(status, 200, body)
		data = body["data"]
		self.assertEqual(data["user"], USER)
		self.assertEqual(data["employee"], self.employee)
		self.assertEqual(data["token"], f"{data['api_key']}:{data['api_secret']}")
		self.assertEqual(get_decrypted_password("User", USER, "api_secret"), data["api_secret"])

	def test_login_with_mobile_in_any_format(self):
		otp = self.request("9876543210")
		status, body = call(auth.verify_otp, mobile_or_email="+91-98765-43210", otp=otp)
		self.assertEqual(status, 200, body)

	def test_otp_is_single_use(self):
		otp = self.request(USER)
		self.assertEqual(call(auth.verify_otp, mobile_or_email=USER, otp=otp)[0], 200)
		self.assertEqual(call(auth.verify_otp, mobile_or_email=USER, otp=otp)[0], 400)

	def test_wrong_otp_then_lockout(self):
		otp = self.request(USER)
		wrong = "000000" if otp != "000000" else "111111"
		max_attempts = frappe.db.get_single_value("HRMS Custom Settings", "otp_max_attempts")
		for _ in range(max_attempts):
			self.assertEqual(call(auth.verify_otp, mobile_or_email=USER, otp=wrong)[0], 400)
		status, _ = call(auth.verify_otp, mobile_or_email=USER, otp=otp)
		self.assertEqual(status, 429)

	def test_unknown_account_gets_same_response_and_no_otp(self):
		status, body = call(auth.request_otp, mobile_or_email="nobody@example.com")
		self.assertEqual(status, 200)
		self.assertEqual(body["message"], auth.GENERIC_SENT_MESSAGE)
		self.assertEqual(self.sent, [])

	def test_new_login_invalidates_previous_secret_and_logout_rotates(self):
		first = call(auth.verify_otp, mobile_or_email=USER, otp=self.request(USER))[1]["data"]
		second = call(auth.verify_otp, mobile_or_email=USER, otp=self.request(USER))[1]["data"]
		self.assertEqual(first["api_key"], second["api_key"])
		self.assertNotEqual(first["api_secret"], second["api_secret"])

		frappe.set_user(USER)
		self.assertEqual(call(auth.logout)[0], 200)
		self.assertNotEqual(get_decrypted_password("User", USER, "api_secret"), second["api_secret"])

	def test_password_login_accepts_email_employee_id_and_mobile(self):
		update_password(USER, PASSWORD)
		for identifier in (USER, self.employee.lower(), "+91-98765-43210"):
			status, body = call(auth.login_with_password, mobile_or_email=identifier, password=PASSWORD)
			self.assertEqual(status, 200, body)
			data = body["data"]
			self.assertEqual(body["message"], "Logged in successfully")
			self.assertEqual(data["user"], USER)
			self.assertEqual(data["employee"], self.employee)
			self.assertEqual(data["token"], f"{data['api_key']}:{data['api_secret']}")

	def test_unknown_identifier_and_wrong_password_share_one_message(self):
		update_password(USER, PASSWORD)
		unknown = call(auth.login_with_password, mobile_or_email="nobody@example.com", password=PASSWORD)
		wrong = call(auth.login_with_password, mobile_or_email=USER, password="not-the-password")
		missing = call(auth.login_with_password, mobile_or_email=USER, password="")
		for status, body in (unknown, wrong, missing):
			self.assertEqual(status, 401, body)
			self.assertEqual(body["message"], auth.INVALID_CREDENTIALS)
			self.assertNotIn("token", body["data"])

	def test_employee_who_cannot_log_in_gets_the_same_message(self):
		update_password(USER, PASSWORD)
		frappe.db.set_value("Employee", self.employee, {"status": "Left", "onboarding_status": ""})
		try:
			status, body = call(auth.login_with_password, mobile_or_email=USER, password=PASSWORD)
			self.assertEqual(status, 401, body)
			self.assertEqual(body["message"], auth.INVALID_CREDENTIALS)
			self.assertNotIn("token", body["data"])
		finally:
			frappe.db.set_value("Employee", self.employee, "status", "Active")

	def test_reset_sets_password_and_signs_in(self):
		otp = self.request(self.employee.lower())
		status, body = call(
			auth.reset_password, mobile_or_email=self.employee.lower(), otp=otp, new_password=PASSWORD
		)
		self.assertEqual(status, 200, body)
		data = body["data"]
		self.assertEqual(data["token"], f"{data['api_key']}:{data['api_secret']}")
		status, body = call(auth.login_with_password, mobile_or_email=USER, password=PASSWORD)
		self.assertEqual(status, 200, body)

	def test_wrong_reset_code_does_not_change_password(self):
		update_password(USER, PASSWORD)
		# A rejected reset rolls the request back. Commit first so that rollback cannot
		# undo the password this test is checking.
		frappe.db.commit()
		otp = self.request(USER)
		wrong = "000000" if otp != "000000" else "111111"
		status, body = call(
			auth.reset_password,
			mobile_or_email=USER,
			otp=wrong,
			new_password="Another-Strong-Pass-2026!",
		)
		self.assertEqual(status, 400, body)
		self.assertEqual(body["message"], auth.INVALID_CODE)
		status, body = call(auth.login_with_password, mobile_or_email=USER, password=PASSWORD)
		self.assertEqual(status, 200, body)

	def test_weak_password_keeps_the_reset_code(self):
		frappe.db.set_single_value("System Settings", "enable_password_policy", 1)
		frappe.db.set_single_value("System Settings", "minimum_password_score", 3)
		frappe.clear_cache(doctype="System Settings")
		otp = self.request(USER)
		status, body = call(auth.reset_password, mobile_or_email=USER, otp=otp, new_password="a")
		self.assertEqual(status, 400, body)
		status, body = call(auth.reset_password, mobile_or_email=USER, otp=otp, new_password=PASSWORD)
		self.assertEqual(status, 200, body)
		status, body = call(auth.login_with_password, mobile_or_email=USER, password=PASSWORD)
		self.assertEqual(status, 200, body)

	def test_request_otp_accepts_employee_id_and_hides_unknown_ids(self):
		otp = self.request(self.employee.lower())
		self.assertRegex(otp, r"^\d{6}$")
		before = len(self.sent)
		status, body = call(auth.request_otp, mobile_or_email="HR-EMP-99999")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"], auth.GENERIC_SENT_MESSAGE)
		self.assertEqual(len(self.sent), before)

	def test_otp_email_is_sent_immediately(self):
		queue = Mock()
		with patch("frappe.email.doctype.email_queue.email_queue.QueueBuilder.process", return_value=queue) as process:
			self._real_deliver(USER, "123456", 300)
		self.assertFalse(process.call_args.kwargs["send_now"])
		queue.send.assert_called_once_with(force_send=True)

	def test_get_my_profile(self):
		frappe.set_user(USER)
		status, body = call(get_my_profile)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["name"], self.employee)
		self.assertIn("Employee", body["data"]["roles"])
