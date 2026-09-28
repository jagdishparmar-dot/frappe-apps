import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ShiftAssignment(Document):
	def validate(self):
		if self.end_date and getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date"))
		if self.status == "Active":
			self.validate_no_overlap()

	def validate_no_overlap(self):
		end = getdate(self.end_date) if self.end_date else getdate("9999-12-31")
		start = getdate(self.start_date)
		overlapping = frappe.db.sql(
			"""
			select name from `tabShift Assignment`
			where employee = %s and status = 'Active' and name != %s
				and start_date <= %s
				and ifnull(end_date, '9999-12-31') >= %s
			limit 1
			""",
			(self.employee, self.name or "", end, start),
		)
		if overlapping:
			frappe.throw(_("This employee already has an active shift assignment that overlaps these dates"))
