import frappe
from frappe import _
from frappe.model.document import Document


class LeaveType(Document):
	def validate(self):
		if (self.max_consecutive_days or 0) < 0:
			frappe.throw(_("Max consecutive days cannot be negative"))
