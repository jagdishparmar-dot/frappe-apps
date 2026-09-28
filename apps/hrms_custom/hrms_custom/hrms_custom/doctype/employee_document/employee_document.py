import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, now_datetime

from hrms_custom.permissions import is_hr
from hrms_custom.utils.notify import CHANNEL_APPROVAL, notify_employee, try_sendmail

DEFAULT_CATEGORY = {
	"ID Proof": "Statutory",
	"Address Proof": "Personal",
	"Offer Letter": "Employment",
	"Appointment Letter": "Employment",
	"Experience Letter": "Employment",
	"Other": "Personal",
}

REVIEWED_STATUSES = ("Verified", "Rejected")


class EmployeeDocument(Document):
	def validate(self):
		if not self.category:
			self.category = DEFAULT_CATEGORY.get(self.document_type, "Personal")
		if self.is_new() or self.has_value_changed("status"):
			self.apply_status_change()

	def apply_status_change(self):
		"""Only HR may set a reviewed status; record who reviewed it and when."""
		if self.status in REVIEWED_STATUSES:
			if not is_hr():
				frappe.throw(_("Only HR can verify or reject documents"), frappe.PermissionError)
			if self.status == "Rejected" and not (self.remarks or "").strip():
				frappe.throw(_("Please add remarks explaining why the document was rejected"))
			self.verified_by = frappe.session.user
			self.verified_on = now_datetime()
			# HR uploading an already-verified document (e.g. an offer letter) needs no notification.
			self.flags.notify_employee = not self.is_new()
		else:
			self.verified_by = None
			self.verified_on = None

	def on_update(self):
		if self.flags.notify_employee:
			self.flags.notify_employee = False
			notify_employee_of_review(self)


def notify_employee_of_review(doc) -> bool:
	user = frappe.db.get_value("Employee", doc.employee, "user_id")
	email = frappe.db.get_value("User", user, "email") if user else None

	verb = "verified" if doc.status == "Verified" else "rejected"
	title = f"Your {doc.document_type} was {verb}"
	notify_employee(
		doc.employee,
		CHANNEL_APPROVAL,
		title,
		f"Your document {doc.file_name or doc.document_type} ({doc.document_type}) was {verb} by HR.",
		route="/documents",
		reference_doctype="Employee Document",
		reference_name=doc.name,
		occurrence_key=f"Employee Document:{doc.name}:{doc.status}",
	)
	if not email:
		return False

	remarks = f"<p>Remarks: {escape_html(doc.remarks)}</p>" if doc.remarks else ""
	action = (
		"<p>Please upload a corrected copy from the Documents screen in the HRMS app.</p>"
		if doc.status == "Rejected"
		else ""
	)
	return try_sendmail(
		recipients=[email],
		subject=title,
		message=(
			f"<p>Your document <b>{escape_html(doc.file_name or doc.document_type)}</b> "
			f"({escape_html(doc.document_type)}) was {verb} by HR.</p>{remarks}{action}"
		),
		reference_doctype="Employee Document",
		reference_name=doc.name,
	)
