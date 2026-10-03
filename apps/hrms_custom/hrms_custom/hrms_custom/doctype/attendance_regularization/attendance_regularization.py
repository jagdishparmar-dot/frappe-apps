import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, now_datetime

from hrms_custom.api.onboarding import get_hr_recipients
from hrms_custom.permissions import is_hr
from hrms_custom.utils.notify import CHANNEL_APPROVAL, notify_employee, try_sendmail
from hrms_custom.utils.regularization import REVIEWED_STATUSES, apply_regularization, validate_request


class AttendanceRegularization(Document):
	def validate(self):
		self._session_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if not is_hr() and self.employee != self._session_employee:
			frappe.throw(_("You can only request regularization for yourself"), frappe.PermissionError)
		if not self.is_new() and not is_hr():
			before = self.get_doc_before_save()
			locked = ("employee", "date", "requested_check_in", "requested_check_out", "reason")
			if before and any(self.has_value_changed(field) for field in locked):
				frappe.throw(_("Open regularizations can only be cancelled, not edited"))
			if self.status != "Cancelled":
				frappe.throw(_("You can only cancel an open regularization"))
			if before and before.status != "Open":
				frappe.throw(_("Only an open regularization can be cancelled"))
		if self.status not in ("Cancelled", "Rejected"):
			validate_request(
				self.employee,
				self.date,
				self.requested_check_in,
				self.requested_check_out,
				self.reason,
				exclude=self.name,
			)
		if self.is_new() or self.has_value_changed("status"):
			self.apply_status_change()

	def apply_status_change(self):
		if self.status in REVIEWED_STATUSES:
			if not is_hr():
				frappe.throw(_("Only HR can approve or reject regularization"), frappe.PermissionError)
			if self.status == "Rejected" and not (self.remarks or "").strip():
				frappe.throw(_("Please add remarks explaining why the request was rejected"))
			self.reviewed_by = frappe.session.user
			self.reviewed_on = now_datetime()
			self.flags.apply_checkins = self.status == "Approved"
			self.flags.notify_employee = not self.is_new()
		elif self.status == "Cancelled":
			before = None if self.is_new() else self.get_doc_before_save()
			if before and before.status != "Open":
				frappe.throw(_("Only an open regularization can be cancelled"))
			self.reviewed_by = None
			self.reviewed_on = None
		else:
			self.reviewed_by = None
			self.reviewed_on = None
			if self.is_new():
				self.flags.notify_hr = True

	def on_update(self):
		if self.flags.apply_checkins:
			self.flags.apply_checkins = False
			applied = apply_regularization(self)
			self.db_set(
				{
					"applied_in": applied.get("in"),
					"applied_out": applied.get("out"),
					"actual_check_in": applied.get("actual_in"),
					"actual_check_out": applied.get("actual_out"),
				},
				update_modified=False,
			)
			self.applied_in = applied.get("in")
			self.applied_out = applied.get("out")
			self.actual_check_in = applied.get("actual_in")
			self.actual_check_out = applied.get("actual_out")
		if self.flags.notify_hr:
			self.flags.notify_hr = False
			notify_hr_of_regularization(self)
		if self.flags.notify_employee:
			self.flags.notify_employee = False
			notify_employee_of_review(self)


def notify_hr_of_regularization(doc) -> bool:
	recipients = get_hr_recipients()
	if not recipients:
		return False
	return try_sendmail(
		recipients=recipients,
		subject=f"Attendance regularization from {doc.employee_name or doc.employee}",
		message=(
			f"{escape_html(doc.employee_name or doc.employee)} requested regularization "
			f"for {doc.date}."
		),
		now=True,
	)


def notify_employee_of_review(doc) -> bool:
	user = frappe.db.get_value("Employee", doc.employee, "user_id")
	email = frappe.db.get_value("User", user, "email") if user else None
	title = f"Your attendance regularization was {doc.status.lower()}"
	body = f"Your regularization for {doc.date} was {doc.status.lower()}." + (
		f" {doc.remarks}" if doc.remarks else ""
	)
	notify_employee(
		doc.employee,
		CHANNEL_APPROVAL,
		title,
		body,
		route="/attendance/regularization",
		reference_doctype="Attendance Regularization",
		reference_name=doc.name,
		occurrence_key=f"Attendance Regularization:{doc.name}:{doc.status}",
	)
	if not email:
		return False
	return try_sendmail(
		recipients=[email],
		subject=title,
		message=(
			f"Your regularization for {doc.date} was {doc.status.lower()}."
			+ (f"<br><br>{escape_html(doc.remarks)}" if doc.remarks else "")
		),
		now=True,
	)
