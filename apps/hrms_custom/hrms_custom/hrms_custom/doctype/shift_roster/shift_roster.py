import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class ShiftRoster(Document):
	def validate(self):
		self.date = getdate(self.date)
		existing = frappe.db.get_value(
			"Shift Roster",
			{"employee": self.employee, "date": self.date, "name": ["!=", self.name or ""]},
			"name",
		)
		if existing:
			frappe.throw(_("A roster row already exists for {0} on {1}").format(self.employee, self.date))
		if not self.location:
			self.location = frappe.db.get_value("Shift Type", self.shift_type, "location")
