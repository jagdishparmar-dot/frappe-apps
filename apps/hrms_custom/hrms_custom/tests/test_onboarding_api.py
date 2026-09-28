import json
from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_years, getdate
from pypdf import PdfWriter
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from hrms_custom.api import auth, onboarding
from hrms_custom.api.attendance import get_punch_status
from hrms_custom.api.profile import get_my_profile
from hrms_custom.hrms_custom.doctype.onboarding_checklist.onboarding_checklist import compute_status
from hrms_custom.tests.utils import call, get_test_company

HR_USER = "onb.hr@example.com"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _blank_pdf() -> bytes:
	writer = PdfWriter()
	writer.add_blank_page(width=72, height=72)
	buffer = BytesIO()
	writer.write(buffer)
	return buffer.getvalue()


PDF = _blank_pdf()


class TestOnboardingApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Onb HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Admin")
		if not frappe.db.exists("Gender", "Female"):
			frappe.get_doc({"doctype": "Gender", "gender": "Female"}).insert(ignore_permissions=True)
		cls.created = []
		cls.counter = 0
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for employee, user in cls.created:
			for doctype in ("Onboarding Checklist", "Employee Document"):
				for name in frappe.get_all(doctype, filters={"employee": employee}, pluck="name"):
					frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
			for name in frappe.get_all(
				"File", filters={"attached_to_doctype": "Employee", "attached_to_name": employee}, pluck="name"
			):
				frappe.delete_doc("File", name, force=True, ignore_permissions=True)
			frappe.delete_doc("Employee", employee, force=True, ignore_permissions=True)
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		patcher = patch("frappe.sendmail")
		self.sendmail = patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_joiner(self, invite=True) -> tuple[str, str]:
		"""An HR-created Inactive employee (name, mobile, email only); optionally invited."""
		type(self).counter += 1
		n = type(self).counter
		email = f"joiner{n}.{frappe.generate_hash(length=5)}@example.com"
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": f"Joiner{n}",
				"company": self.company,
				"status": "Inactive",
				"date_of_joining": getdate(),
				"personal_email": email,
				"cell_number": f"+91 70000 {n:05d}",
			}
		).insert(ignore_permissions=True)
		self.created.append((employee.name, email))
		frappe.db.commit()
		if invite:
			frappe.set_user(HR_USER)
			status, body = call(onboarding.invite_employee, employee=employee.name)
			self.assertEqual(status, 200, body)
			frappe.db.commit()
		frappe.set_user("Administrator")
		return employee.name, email

	def upload(self, employee, document_type="ID Proof", content=PNG, filename="id.png"):
		return onboarding.save_onboarding_document(employee, document_type, filename, content)

	def valid_payload(self, documents):
		return {
			"personal_details": json.dumps(
				{"first_name": "Asha", "last_name": "Rao", "gender": "Female", "date_of_birth": "1995-04-12"}
			),
			"contact_details": {"cell_number": "+91 98111 22334", "current_address": "12 MG Road"},
			"bank_details": {"account_holder_name": "Asha Rao", "bank_account_no": "123456789012", "ifsc_code": "hdfc0001234"},
			"emergency_contact": {"emergency_contact_name": "Ravi", "emergency_contact_phone": "9811122335"},
			"documents": json.dumps(documents),
		}

	def test_invite_creates_user_and_marks_invited(self):
		employee, email = self.make_joiner()
		doc = frappe.get_doc("Employee", employee)
		self.assertEqual(doc.user_id, email)
		self.assertEqual(doc.status, "Inactive")
		self.assertEqual(doc.onboarding_status, "Invited")
		self.assertTrue(frappe.db.get_value("User", email, "enabled"))
		self.assertEqual(self.sendmail.call_args.kwargs["recipients"], [email])

	def test_invite_succeeds_without_outgoing_email(self):
		employee, _ = self.make_joiner(invite=False)
		self.sendmail.side_effect = frappe.OutgoingEmailError("no account")
		frappe.set_user(HR_USER)
		status, body = call(onboarding.invite_employee, employee=employee)
		self.assertEqual(status, 200, body)
		self.assertFalse(body["data"]["email_sent"])
		self.assertIn("could not be sent", body["message"])
		self.assertEqual(frappe.db.get_value("Employee", employee, "onboarding_status"), "Invited")

	def test_invite_requires_hr_and_email(self):
		employee, _ = self.make_joiner(invite=False)
		_, other_joiner = self.make_joiner()
		frappe.set_user(other_joiner)
		self.assertEqual(call(onboarding.invite_employee, employee=employee)[0], 403)

		frappe.set_user("Administrator")
		frappe.db.set_value("Employee", employee, "personal_email", None)
		frappe.db.commit()
		frappe.set_user(HR_USER)
		status, body = call(onboarding.invite_employee, employee=employee)
		self.assertEqual(status, 400, body)

	def test_invited_joiner_can_log_in_but_not_punch(self):
		employee, email = self.make_joiner()
		frappe.set_user("Guest")
		sent = []
		with patch.object(auth, "_deliver", side_effect=lambda ident, otp, exp: sent.append(otp)):
			self.assertEqual(call(auth.request_otp, mobile_or_email=email)[0], 200)
		status, body = call(auth.verify_otp, mobile_or_email=email, otp=sent[-1])
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["employee"], employee)

		frappe.set_user(email)
		status, body = call(get_my_profile)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["onboarding_status"], "Invited")
		self.assertEqual(call(get_punch_status)[0], 403)

	def test_get_onboarding_form_is_prefilled(self):
		employee, email = self.make_joiner()
		frappe.set_user(email)
		status, body = call(onboarding.get_onboarding_form)
		self.assertEqual(status, 200, body)
		data = body["data"]
		self.assertEqual(data["employee"], employee)
		self.assertEqual(data["sections"]["contact_details"]["personal_email"], email)
		self.assertIn("ID Proof", data["document_types"])
		self.assertEqual(data["documents"], [])

	def test_upload_validation(self):
		employee, _ = self.make_joiner()
		for kwargs, message in (
			({"filename": "id.exe"}, "Only PDF"),
			({"filename": "id.pdf", "content": PNG}, "does not match"),
			({"content": b""}, "empty"),
			({"content": PNG + b"\x00" * onboarding.MAX_UPLOAD_BYTES}, "too large"),
			({"document_type": "Passport Photo"}, "valid document type"),
		):
			with self.assertRaises(onboarding.ApiError) as ctx:
				self.upload(employee, **kwargs)
			self.assertIn(message, ctx.exception.message)

		self.assertEqual(self.upload(employee)["category"], "Statutory")
		document = self.upload(employee, "Address Proof", PDF, "bill.pdf")
		self.assertEqual(document["category"], "Personal")
		file_url = frappe.db.get_value("Employee Document", document["name"], "file")
		self.assertTrue(file_url.startswith("/private/files/"))

	def test_upload_endpoint_reads_multipart_file(self):
		employee, email = self.make_joiner()
		frappe.set_user(email)
		builder = EnvironBuilder(
			method="POST", base_url="http://test.localhost", data={"file": (BytesIO(PNG), "aadhaar.png")}
		)
		with patch.object(frappe.local, "request", Request(builder.get_environ()), create=True):
			status, body = call(onboarding.upload_onboarding_document, document_type="ID Proof")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["file_name"], "aadhaar.png")
		self.assertEqual(frappe.db.get_value("Employee Document", body["data"]["name"], "employee"), employee)

	def test_submit_reports_field_errors(self):
		employee, email = self.make_joiner()
		frappe.set_user(email)
		status, body = call(
			onboarding.submit_onboarding_form,
			personal_details={"first_name": " ", "date_of_birth": str(add_days(getdate(), 1))},
			contact_details={"cell_number": "123"},
			bank_details={"bank_account_no": "12ab", "ifsc_code": "BAD"},
			documents=[],
		)
		self.assertEqual(status, 400, body)
		errors = body["data"]["errors"]
		for field in ("first_name", "date_of_birth", "cell_number", "bank_account_no", "ifsc_code", "documents"):
			self.assertIn(field, errors)
		self.assertEqual(frappe.db.get_value("Employee", employee, "onboarding_status"), "Invited")

	def test_submit_requires_an_id_proof_owned_by_the_joiner(self):
		employee, email = self.make_joiner()
		other, _ = self.make_joiner()
		address = self.upload(employee, "Address Proof")
		foreign_id = self.upload(other, "ID Proof")
		frappe.db.commit()

		frappe.set_user(email)
		body = call(onboarding.submit_onboarding_form, **self.valid_payload([address["name"]]))[1]
		self.assertEqual(body["data"]["errors"]["documents"], "Upload at least one ID proof")
		body = call(onboarding.submit_onboarding_form, **self.valid_payload([foreign_id["name"]]))[1]
		self.assertIn("could not be found", body["data"]["errors"]["documents"])

	def test_successful_submission(self):
		employee, email = self.make_joiner()
		document = self.upload(employee)
		frappe.db.commit()

		frappe.set_user(email)
		status, body = call(onboarding.submit_onboarding_form, **self.valid_payload([document["name"]]))
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"], "Submitted — pending verification")
		frappe.db.commit()

		doc = frappe.get_doc("Employee", employee)
		self.assertEqual(doc.onboarding_status, "Pending Verification")
		self.assertEqual(doc.employee_name, "Asha Rao")
		self.assertEqual(doc.ifsc_code, "HDFC0001234")
		self.assertEqual(str(doc.date_of_birth), "1995-04-12")
		self.assertIsNotNone(doc.onboarding_submitted_on)
		self.assertEqual(doc.status, "Inactive")

		checklist = frappe.get_doc("Onboarding Checklist", body["data"]["checklist"])
		self.assertEqual(checklist.employee, employee)
		self.assertEqual(len(checklist.tasks), len(onboarding.DEFAULT_CHECKLIST_TASKS))
		self.assertEqual(checklist.status, "Not Started")
		self.assertIn(HR_USER, self.sendmail.call_args.kwargs["recipients"])

		self.assertEqual(call(onboarding.submit_onboarding_form, **self.valid_payload([document["name"]]))[0], 409)
		self.assertEqual(call(onboarding.delete_onboarding_document, document=document["name"])[0], 403)
		self.assertEqual(call(get_my_profile)[1]["data"]["onboarding_status"], "Pending Verification")

	def test_joiner_cannot_write_protected_fields(self):
		employee, email = self.make_joiner()
		document = self.upload(employee)
		frappe.db.commit()

		frappe.set_user(email)
		payload = self.valid_payload([document["name"]])
		payload["personal_details"] = json.dumps(
			{"first_name": "Asha", "date_of_birth": "1995-04-12", "status": "Active", "company": "Other"}
		)
		self.assertEqual(call(onboarding.submit_onboarding_form, **payload)[0], 200)
		frappe.db.commit()
		self.assertEqual(frappe.db.get_value("Employee", employee, "status"), "Inactive")
		self.assertEqual(frappe.db.get_value("Employee", employee, "company"), self.company)

	def test_delete_only_own_documents(self):
		employee, email = self.make_joiner()
		other, _ = self.make_joiner()
		mine = self.upload(employee)
		theirs = self.upload(other)
		frappe.db.commit()

		frappe.set_user(email)
		self.assertEqual(call(onboarding.delete_onboarding_document, document=theirs["name"])[0], 404)
		self.assertEqual(call(onboarding.delete_onboarding_document, document=mine["name"])[0], 200)
		self.assertFalse(frappe.db.exists("Employee Document", mine["name"]))

	def test_verified_employee_can_be_activated(self):
		employee, _ = self.make_joiner()
		doc = frappe.get_doc("Employee", employee)
		doc.update(
			{"onboarding_status": "Verified", "status": "Active", "date_of_birth": add_years(getdate(), -25)}
		)
		doc.save()
		self.assertEqual(frappe.db.get_value("Employee", employee, "status"), "Active")


class TestChecklistStatus(IntegrationTestCase):
	def test_compute_status(self):
		self.assertEqual(compute_status([]), "Not Started")
		self.assertEqual(compute_status(["Pending", "Pending"]), "Not Started")
		self.assertEqual(compute_status(["Done", "Pending"]), "In Progress")
		self.assertEqual(compute_status(["Done", "Done"]), "Completed")
