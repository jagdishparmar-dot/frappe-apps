import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import escape_html, now_datetime

from hrms_custom.api.onboarding import get_hr_recipients
from hrms_custom.permissions import is_hr
from hrms_custom.utils.leave import preview_application
from hrms_custom.utils.notify import try_sendmail

REVIEWED_STATUSES = ("Approved", "Rejected")


class LeaveApplication(Document):
	def validate(self):
		self._session_employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
		if not is_hr() and self.employee != self._session_employee:
			frappe.throw(_("You can only apply leave for yourself"), frappe.PermissionError)
		if not self.is_new() and not is_hr():
			before = self.get_doc_before_save()
			locked = ("employee", "leave_type", "from_date", "to_date", "half_day", "half_day_date", "reason", "total_days")
			if before and any(self.has_value_changed(field) for field in locked):
				frappe.throw(_("Open leave applications can only be cancelled, not edited"))
			if self.status != "Cancelled":
				frappe.throw(_("You can only cancel an open leave application"))
			if before and before.status != "Open":
				frappe.throw(_("Only an open leave application can be cancelled"))
		company = frappe.db.get_value("Employee", self.employee, "company")
		preview = preview_application(
			self.employee,
			company,
			self.leave_type,
			self.from_date,
			self.to_date,
			half_day=self.half_day,
			half_day_date=self.half_day_date,
			exclude=self.name,
			check_balance=self.status not in ("Cancelled", "Rejected"),
		)
		self.total_days = preview["total_days"]
		if self.half_day and not self.half_day_date:
			self.half_day_date = preview["half_day_date"]
		if self.is_new() or self.has_value_changed("status"):
			self.apply_status_change()

	def apply_status_change(self):
		if self.status in REVIEWED_STATUSES:
			if not is_hr():
				frappe.throw(_("Only HR can approve or reject leave"), frappe.PermissionError)
			if self.status == "Rejected" and not (self.remarks or "").strip():
				frappe.throw(_("Please add remarks explaining why the leave was rejected"))
			self.reviewed_by = frappe.session.user
			self.reviewed_on = now_datetime()
			self.flags.notify_employee = not self.is_new()
		elif self.status == "Cancelled":
			before = None if self.is_new() else self.get_doc_before_save()
			if before and before.status != "Open":
				frappe.throw(_("Only an open leave application can be cancelled"))
			self.reviewed_by = None
			self.reviewed_on = None
		else:
			self.reviewed_by = None
			self.reviewed_on = None
			if self.is_new():
				self.flags.notify_hr = True

	def on_update(self):
		if self.flags.notify_hr:
			self.flags.notify_hr = False
			notify_hr_of_application(self)
		if self.flags.notify_employee:
			self.flags.notify_employee = False
			notify_employee_of_review(self)


def notify_hr_of_application(doc) -> bool:
	recipients = get_hr_recipients()
	if not recipients:
		return False
	return try_sendmail(
		recipients=recipients,
		subject=f"Leave application from {doc.employee_name or doc.employee}",
		message=(
			f"{escape_html(doc.employee_name or doc.employee)} applied for "
			f"{escape_html(doc.leave_type)} ({doc.total_days:g} day(s)) "
			f"from {doc.from_date} to {doc.to_date}."
		),
		now=True,
	)


def notify_employee_of_review(doc) -> bool:
	user = frappe.db.get_value("Employee", doc.employee, "user_id")
	email = frappe.db.get_value("User", user, "email") if user else None
	if not email:
		return False
	return try_sendmail(
		recipients=[email],
		subject=f"Your leave application was {doc.status.lower()}",
		message=(
			f"Your {escape_html(doc.leave_type)} request ({doc.from_date} – {doc.to_date}) "
			f"was {doc.status.lower()}."
			+ (f"<br><br>{escape_html(doc.remarks)}" if doc.remarks else "")
		),
		now=True,
	)
