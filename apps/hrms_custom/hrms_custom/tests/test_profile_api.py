from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_years, getdate
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from hrms_custom.api import profile
from hrms_custom.tests.utils import call, get_test_company, make_employee_user

EMPLOYEE_USER = "profile.employee@example.com"
OTHER_USER = "profile.other@example.com"
HR_USER = "profile.hr@example.com"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _multipart(filename: str, content: bytes) -> Request:
	builder = EnvironBuilder(
		method="POST", base_url="http://test.localhost", data={"file": (BytesIO(content), filename)}
	)
	return Request(builder.get_environ())


class TestProfileApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, company, "Priya", mobile="9000011000")
		cls.other = make_employee_user(OTHER_USER, company, "Other", mobile="9000011001")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Profile HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Executive")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for employee in (cls.employee, cls.other):
			for name in frappe.get_all("Profile Update Request", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Profile Update Request", name, force=True, ignore_permissions=True)
			frappe.db.set_value("Employee", employee, "image", None)
			for name in frappe.get_all(
				"File", filters={"attached_to_doctype": "Employee", "attached_to_name": employee}, pluck="name"
			):
				frappe.delete_doc("File", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Profile Update Request", filters={"employee": self.employee}, pluck="name"):
			frappe.delete_doc("Profile Update Request", name, force=True, ignore_permissions=True)
		frappe.db.set_value(
			"Employee",
			self.employee,
			{
				"personal_email": None,
				"bank_account_no": None,
				"ifsc_code": None,
				"bank_name": None,
				"nationality": None,
				"cell_number": "9000011000",
				"image": None,
			},
		)
		frappe.db.commit()
		patcher = patch("frappe.sendmail")
		self.sendmail = patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")

	def request_update(self, user, changes, **kwargs):
		frappe.set_user(user)
		return call(profile.request_profile_update, changes=changes, **kwargs)

	def test_get_my_profile_includes_values_and_no_pending_request(self):
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(profile.get_my_profile)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["name"], self.employee)
		self.assertEqual(body["data"]["values"]["first_name"], "Priya")
		self.assertIsNone(body["data"]["pending_request"])
		self.assertIn("personal_details", body["data"]["sections"])
		self.assertFalse(body["data"]["has_image"])

	def test_request_does_not_write_employee_until_hr_approves(self):
		status, body = self.request_update(EMPLOYEE_USER, {"personal_email": "priya.new@example.com"})
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Pending")
		self.assertEqual(body["data"]["changes"]["personal_email"]["to"], "priya.new@example.com")
		self.assertIsNone(frappe.db.get_value("Employee", self.employee, "personal_email"))
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(profile.get_my_profile)[1]["data"]["pending_request"]["name"], body["data"]["name"])

	def test_unknown_and_empty_changes_are_rejected(self):
		status, body = self.request_update(EMPLOYEE_USER, {"department": "Sales"})
		self.assertEqual(status, 400, body)
		self.assertIn("department", body["data"]["errors"])

		status, body = self.request_update(EMPLOYEE_USER, {"personal_email": None})
		self.assertEqual(status, 400, body)

	def test_invalid_bank_is_rejected_and_second_pending_is_blocked(self):
		status, body = self.request_update(EMPLOYEE_USER, {"ifsc_code": "BAD", "bank_account_no": "12"})
		self.assertEqual(status, 400, body)
		self.assertIn("ifsc_code", body["data"]["errors"])

		status, body = self.request_update(
			EMPLOYEE_USER, {"bank_account_no": "123456789012", "ifsc_code": "HDFC0001234", "bank_name": "HDFC"}
		)
		self.assertEqual(status, 200, body)
		frappe.db.commit()
		status, body = self.request_update(EMPLOYEE_USER, {"nationality": "Indian"})
		self.assertEqual(status, 409, body)

	def test_only_hr_can_review_and_approve_applies_fields(self):
		name = self.request_update(EMPLOYEE_USER, {"personal_email": "priya.new@example.com"})[1]["data"]["name"]
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(profile.review_profile_update, request=name, status="Approved")[0], 403)

		frappe.set_user(HR_USER)
		status, body = call(profile.review_profile_update, request=name, status="Approved")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Approved")
		self.assertEqual(body["data"]["reviewed_by"], HR_USER)
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "personal_email"), "priya.new@example.com")
		self.sendmail.assert_called()
		self.assertTrue(any("approved" in (c.kwargs.get("subject") or "") for c in self.sendmail.call_args_list))

	def test_reject_requires_remarks_and_leaves_employee_unchanged(self):
		name = self.request_update(EMPLOYEE_USER, {"nationality": "Indian"})[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(HR_USER)
		self.assertEqual(call(profile.review_profile_update, request=name, status="Rejected")[0], 400)
		status, body = call(profile.review_profile_update, request=name, status="Rejected", remarks="Need passport copy")
		self.assertEqual(status, 200, body)
		self.assertIsNone(frappe.db.get_value("Employee", self.employee, "nationality"))

	def test_employee_cancels_own_pending_request(self):
		name = self.request_update(EMPLOYEE_USER, {"nationality": "Indian"})[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(EMPLOYEE_USER)
		status, body = call(profile.cancel_profile_update, request=name)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Cancelled")
		self.assertIsNone(call(profile.get_my_profile)[1]["data"]["pending_request"])

	def test_employee_cannot_list_or_cancel_anothers_request(self):
		name = self.request_update(EMPLOYEE_USER, {"nationality": "Indian"})[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(OTHER_USER)
		self.assertEqual(call(profile.list_profile_updates, employee=self.employee)[0], 403)
		self.assertEqual(call(profile.cancel_profile_update, request=name)[0], 404)
		frappe.set_user(HR_USER)
		status, body = call(profile.list_profile_updates, status="Pending")
		self.assertEqual(status, 200, body)
		self.assertTrue(any(r["name"] == name for r in body["data"]["requests"]))

	def test_desk_approve_applies_and_notifies(self):
		name = self.request_update(EMPLOYEE_USER, {"cell_number": "9000011999"})[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(HR_USER)
		doc = frappe.get_doc("Profile Update Request", name)
		doc.status = "Approved"
		doc.save()
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "cell_number"), "9000011999")
		self.sendmail.assert_called()

	def test_employee_cannot_approve_even_with_ignore_permissions(self):
		name = self.request_update(EMPLOYEE_USER, {"nationality": "Indian"})[1]["data"]["name"]
		frappe.db.commit()
		frappe.set_user(EMPLOYEE_USER)
		doc = frappe.get_doc("Profile Update Request", name)
		doc.status = "Approved"
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)

	def test_approve_succeeds_without_outgoing_email(self):
		name = self.request_update(EMPLOYEE_USER, {"nationality": "Indian"})[1]["data"]["name"]
		frappe.db.commit()
		self.sendmail.side_effect = frappe.OutgoingEmailError("no account")
		frappe.set_user(HR_USER)
		status, body = call(profile.review_profile_update, request=name, status="Approved")
		self.assertEqual(status, 200, body)
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "nationality"), "Indian")

	def test_joiner_cannot_request_a_profile_update(self):
		company = get_test_company()
		email = "profile.joiner@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Joiner", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		joiner = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Joiner",
				"date_of_joining": add_years(getdate(), -0),
				"company": company,
				"status": "Inactive",
				"onboarding_status": "Invited",
				"user_id": email,
				"cell_number": "9000011002",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.set_user(email)
		self.assertEqual(call(profile.request_profile_update, changes={"nationality": "Indian"})[0], 403)
		frappe.set_user("Administrator")
		frappe.delete_doc("Employee", joiner.name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def upload_photo(self, user, filename="photo.png", content=PNG):
		frappe.set_user(user)
		with patch.object(frappe.local, "request", _multipart(filename, content), create=True):
			return call(profile.upload_profile_image)

	def test_employee_uploads_downloads_and_removes_profile_photo(self):
		status, body = self.upload_photo(EMPLOYEE_USER)
		self.assertEqual(status, 200, body)
		self.assertTrue(body["data"]["has_image"])
		self.assertTrue(body["data"]["image"])
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "image"), body["data"]["image"])
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		response = profile.download_profile_image()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.mimetype, "image/png")
		self.assertEqual(response.get_data(), PNG)

		status, body = call(profile.get_my_profile)
		self.assertEqual(status, 200, body)
		self.assertTrue(body["data"]["has_image"])

		status, body = call(profile.remove_profile_image)
		self.assertEqual(status, 200, body)
		self.assertFalse(body["data"]["has_image"])
		self.assertFalse(frappe.db.get_value("Employee", self.employee, "image"))

	def test_profile_photo_rejects_non_images(self):
		status, body = self.upload_photo(EMPLOYEE_USER, filename="id.pdf", content=b"%PDF-1.4")
		self.assertEqual(status, 400, body)
		self.assertIn("JPG", body["message"])

