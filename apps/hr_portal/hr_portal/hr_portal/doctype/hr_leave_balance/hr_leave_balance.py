import frappe
from frappe.model.document import Document


class HRLeaveBalance(Document):
	def validate(self):
		key = frappe.db.exists(
			"HR Leave Balance",
			{
				"employee": self.employee,
				"leave_type": self.leave_type,
				"year": self.year,
				"name": ("!=", self.name),
			},
		)
		if key:
			frappe.throw("Leave balance already exists for this employee, type, and year.")
