from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from hrms_custom.api import documents
from hrms_custom.tests.utils import call, get_test_company, make_employee_user
from hrms_custom.utils.documents import save_employee_document

EMPLOYEE_USER = "docs.employee@example.com"
OTHER_USER = "docs.other@example.com"
HR_USER = "docs.hr@example.com"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _multipart(filename: str, content: bytes) -> Request:
	builder = EnvironBuilder(
		method="POST", base_url="http://test.localhost", data={"file": (BytesIO(content), filename)}
	)
	return Request(builder.get_environ())


class TestDocumentsApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		company = get_test_company()
		cls.employee = make_employee_user(EMPLOYEE_USER, company, "Docs")
		cls.other = make_employee_user(OTHER_USER, company, "Other")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Docs HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Executive")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for employee in (cls.employee, cls.other):
			for name in frappe.get_all("Employee Document", filters={"employee": employee}, pluck="name"):
				frappe.delete_doc("Employee Document", name, force=True, ignore_permissions=True)
			for name in frappe.get_all(
				"File", filters={"attached_to_doctype": "Employee", "attached_to_name": employee}, pluck="name"
			):
				frappe.delete_doc("File", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		patcher = patch("frappe.sendmail")
		self.sendmail = patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_document(self, employee=None, document_type="ID Proof") -> str:
		name = save_employee_document(employee or self.employee, document_type, "id.png", PNG)["name"]
		frappe.db.commit()
		return name

	def upload(self, user, document_type="ID Proof", filename="id.png", content=PNG, **kwargs):
		frappe.set_user(user)
		with patch.object(frappe.local, "request", _multipart(filename, content), create=True):
			return call(documents.upload_document, document_type=document_type, **kwargs)

	def test_employee_uploads_and_lists_own_documents(self):
		status, body = self.upload(EMPLOYEE_USER, "Address Proof")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["status"], "Pending")
		self.assertEqual(body["data"]["category"], "Personal")
		frappe.db.commit()

		status, body = call(documents.list_documents)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["employee"], self.employee)
		self.assertIn("Address Proof", [d["document_type"] for d in body["data"]["documents"]])

	def test_upload_rejects_disguised_files(self):
		status, body = self.upload(EMPLOYEE_USER, filename="id.pdf", content=PNG)
		self.assertEqual(status, 400, body)
		self.assertIn("does not match", body["message"])

	def test_employee_cannot_list_or_download_others(self):
		theirs = self.make_document(self.other)
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(documents.list_documents, employee=self.other)[0], 403)
		self.assertEqual(call(documents.download_document, document=theirs)[0], 404)

	def test_hr_can_list_any_employee(self):
		self.make_document(self.other)
		frappe.set_user(HR_USER)
		status, body = call(documents.list_documents, employee=self.other)
		self.assertEqual(status, 200, body)
		self.assertTrue(body["data"]["documents"])

	def test_only_hr_can_verify(self):
		name = self.make_document()
		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(documents.verify_document, document=name, status="Verified")[0], 403)
		self.assertEqual(frappe.db.get_value("Employee Document", name, "status"), "Pending")

	def test_verify_records_reviewer_and_emails_employee(self):
		name = self.make_document()
		frappe.set_user(HR_USER)
		status, body = call(documents.verify_document, document=name, status="Verified")
		self.assertEqual(status, 200, body)
		frappe.db.commit()

		row = frappe.db.get_value("Employee Document", name, ["status", "verified_by", "verified_on"], as_dict=True)
		self.assertEqual(row.status, "Verified")
		self.assertEqual(row.verified_by, HR_USER)
		self.assertIsNotNone(row.verified_on)
		self.assertEqual(self.sendmail.call_args.kwargs["recipients"], [EMPLOYEE_USER])
		self.assertIn("verified", self.sendmail.call_args.kwargs["subject"])

	def test_reject_requires_remarks(self):
		name = self.make_document()
		frappe.set_user(HR_USER)
		status, body = call(documents.verify_document, document=name, status="Rejected")
		self.assertEqual(status, 400, body)
		self.assertIn("remarks", body["message"])

		status, body = call(documents.verify_document, document=name, status="Rejected", remarks="Blurry photo")
		self.assertEqual(status, 200, body)
		self.assertEqual(body["data"]["remarks"], "Blurry photo")
		self.assertIn("Blurry photo", self.sendmail.call_args.kwargs["message"])

	def test_invalid_status_and_unknown_document(self):
		frappe.set_user(HR_USER)
		self.assertEqual(call(documents.verify_document, document="nope", status="Verified")[0], 404)
		name = self.make_document()
		self.assertEqual(call(documents.verify_document, document=name, status="Pending")[0], 400)

	def test_desk_status_change_also_notifies_and_is_hr_only(self):
		name = self.make_document()
		frappe.set_user(HR_USER)
		doc = frappe.get_doc("Employee Document", name)
		doc.status = "Verified"
		doc.save()
		self.assertTrue(self.sendmail.called)

		frappe.set_user(EMPLOYEE_USER)
		doc = frappe.get_doc("Employee Document", name)
		doc.status = "Rejected"
		doc.remarks = "self-reject"
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)

	def test_verify_succeeds_without_outgoing_email(self):
		name = self.make_document()
		self.sendmail.side_effect = frappe.OutgoingEmailError("no account")
		frappe.set_user(HR_USER)
		status, body = call(documents.verify_document, document=name, status="Verified")
		self.assertEqual(status, 200, body)

	def test_delete_only_pending_own_documents(self):
		pending = self.make_document()
		verified = self.make_document()
		frappe.set_user(HR_USER)
		call(documents.verify_document, document=verified, status="Verified")
		frappe.db.commit()

		frappe.set_user(EMPLOYEE_USER)
		self.assertEqual(call(documents.delete_document, document=verified)[0], 409)
		self.assertEqual(call(documents.delete_document, document=pending)[0], 200)
		self.assertFalse(frappe.db.exists("Employee Document", pending))

	def test_reupload_replaces_a_rejected_document(self):
		rejected = self.make_document()
		pending = self.make_document()
		frappe.set_user(HR_USER)
		call(documents.verify_document, document=rejected, status="Rejected", remarks="Expired")
		frappe.db.commit()

		self.assertEqual(self.upload(EMPLOYEE_USER, replaces=pending)[0], 409)
		status, body = self.upload(EMPLOYEE_USER, replaces=rejected)
		self.assertEqual(status, 200, body)
		self.assertFalse(frappe.db.exists("Employee Document", rejected))
		self.assertEqual(body["data"]["status"], "Pending")

	def test_download_returns_file_for_owner_and_hr(self):
		name = self.make_document()
		for user in (EMPLOYEE_USER, HR_USER):
			frappe.set_user(user)
			response = documents.download_document(document=name)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.mimetype, "image/png")
			self.assertEqual(response.get_data(), PNG)

	def test_hr_upload_of_verified_document_does_not_notify(self):
		frappe.set_user(HR_USER)
		frappe.get_doc(
			{
				"doctype": "Employee Document",
				"employee": self.employee,
				"document_type": "Offer Letter",
				"status": "Verified",
				"file": "/private/files/offer.pdf",
			}
		).insert()
		self.assertFalse(self.sendmail.called)
