import frappe
from frappe.model.document import Document
from frappe.utils import cint


class HRSettings(Document):
	def validate(self):
		padding = cint(self.employee_code_padding)
		sequence = cint(self.employee_code_next_sequence)
		late_grace = cint(self.late_grace_minutes)

		if self.employee_code_padding is not None and padding < 1:
			frappe.throw("Employee code padding must be at least 1")
		if self.employee_code_next_sequence is not None and sequence < 1:
			frappe.throw("Next sequence must be at least 1")
		if self.late_grace_minutes is not None and late_grace < 0:
			frappe.throw("Late grace cannot be negative")
