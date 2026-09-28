import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, now_datetime

from hrms_custom.permissions import is_hr
from hrms_custom.utils.employee_fields import (
	EDITABLE_FIELDS,
	apply_changes,
	changes_summary,
	FIELD_LABELS,
)
from hrms_custom.utils.notify import try_sendmail

REVIEWED_STATUSES = ("Approved", "Rejected")


class ProfileUpdateRequest(Document):
	def validate(self):
		self.changes = self.parsed_changes()
		self.validate_changes()
		self.summary = changes_summary(self.changes)
		if not self.requested_by:
			self.requested_by = frappe.session.user
		if self.is_new() or self.has_value_changed("status"):
			self.apply_status_change()

	def parsed_changes(self) -> dict:
		raw = frappe.parse_json(self.field_changes) if self.field_changes else {}
		if not isinstance(raw, dict) or not raw:
			frappe.throw(_("Add at least one field change"))
		return raw

	def validate_changes(self):
		if not self.is_new() and self.has_value_changed("field_changes"):
			frappe.throw(_("Changes cannot be edited. Cancel this request and submit a new one."))
		unknown = [field for field in self.changes if field not in EDITABLE_FIELDS]
		if unknown:
			frappe.throw(_("{0} cannot be changed from a profile update").format(unknown[0]))
		if self.is_new() and self.status == "Pending":
			existing = frappe.db.get_value(
				"Profile Update Request",
				{"employee": self.employee, "status": "Pending", "name": ("!=", self.name or "")},
				"name",
			)
			if existing:
				frappe.throw(_("A pending profile update already exists for this employee"))

	def apply_status_change(self):
		if self.status in REVIEWED_STATUSES:
			if not is_hr():
				frappe.throw(_("Only HR can approve or reject profile updates"), frappe.PermissionError)
			if self.status == "Rejected" and not (self.remarks or "").strip():
				frappe.throw(_("Please add remarks explaining why the request was rejected"))
			self.reviewed_by = frappe.session.user
			self.reviewed_on = now_datetime()
			self.flags.apply_to_employee = self.status == "Approved"
			self.flags.notify_employee = not self.is_new()
		elif self.status == "Cancelled":
			if self.has_value_changed("status") and self.get_doc_before_save() and self.get_doc_before_save().status != "Pending":
				frappe.throw(_("Only a pending request can be cancelled"))
			self.reviewed_by = None
			self.reviewed_on = None
		else:
			self.reviewed_by = None
			self.reviewed_on = None

	def on_update(self):
		if self.flags.apply_to_employee:
			self.flags.apply_to_employee = False
			apply_changes(self.employee, self.changes)
		if self.flags.notify_employee:
			self.flags.notify_employee = False
			notify_employee_of_review(self)


def notify_employee_of_review(doc) -> bool:
	user = frappe.db.get_value("Employee", doc.employee, "user_id")
	email = frappe.db.get_value("User", user, "email") if user else None
	if not email:
		return False

	verb = "approved" if doc.status == "Approved" else "rejected"
	remarks = f"<p>Remarks: {escape_html(doc.remarks)}</p>" if doc.remarks else ""
	items = "".join(
		f"<li>{escape_html(FIELD_LABELS.get(field, field))}</li>" for field in (doc.changes or {})
	)
	return try_sendmail(
		recipients=[email],
		subject=f"Your profile update was {verb}",
		message=(
			f"<p>HR {verb} your profile update request.</p>"
			f"<ul>{items}</ul>{remarks}"
		),
		reference_doctype="Profile Update Request",
		reference_name=doc.name,
	)
