import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate


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
		if cint(self.is_week_off):
			self.shift_type = None
			self.location = None
		elif not self.shift_type:
			frappe.throw(_("Shift Type is required unless Week Off is set"))
		elif not self.location:
			self.location = frappe.db.get_value("Shift Type", self.shift_type, "location")
