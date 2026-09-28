from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import get_decrypted_password

from hrms_custom.api import auth
from hrms_custom.api.profile import get_my_profile
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

USER = "otp.tester@example.com"
MOBILE = "+91 98765 43210"


class TestOtpAuth(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.employee = make_employee_user(USER, get_test_company(), "Otp", mobile=MOBILE)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Guest")
		self.sent = []
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

	def test_get_my_profile(self):
		frappe.set_user(USER)
		status, body = call(get_my_profile)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["name"], self.employee)
		self.assertIn("Employee", body["data"]["roles"])
