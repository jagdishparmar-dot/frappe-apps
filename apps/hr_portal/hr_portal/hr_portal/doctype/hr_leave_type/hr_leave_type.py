import frappe
from frappe.model.document import Document


class HRLeaveType(Document):
	def validate(self):
		self.code = (self.code or "").strip().upper()
		if not self.code:
			frappe.throw("Leave type code is required")
