import frappe
from frappe.model.document import Document


class HRShiftAssignment(Document):
	def validate(self):
		self.sequence = int(self.sequence or 1)
		if self.sequence < 1 or self.sequence > 10:
			frappe.throw("Sequence must be between 1 and 10")
		existing = frappe.db.exists(
			"HR Shift Assignment",
			{
				"employee": self.employee,
				"assignment_date": self.assignment_date,
				"sequence": self.sequence,
				"status": "Scheduled",
				"name": ["!=", self.name or ""],
			},
		)
		if existing:
			frappe.throw("This employee already has a scheduled assignment for that date and sequence")
