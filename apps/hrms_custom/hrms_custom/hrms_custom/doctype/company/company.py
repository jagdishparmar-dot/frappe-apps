import frappe
from frappe import _
from frappe.model.document import Document


class Company(Document):
	def validate(self):
		self.abbr = (self.abbr or "").strip().upper()
		self.validate_default_shift()
		self.validate_default_week_off_weekdays()

	def validate_default_shift(self):
		if not self.default_shift:
			return
		if not frappe.db.exists("Shift Type", self.default_shift):
			frappe.throw(_("Default Shift {0} does not exist").format(self.default_shift))

	def validate_default_week_off_weekdays(self):
		from hrms_custom.utils.employee_defaults import parse_week_off_weekdays

		raw = (self.default_week_off_weekdays or "").strip()
		if not raw:
			return
		weekdays, invalid = parse_week_off_weekdays(raw)
		if invalid:
			frappe.throw(_("Unknown week off day: {0}").format(invalid[0]))
		if not weekdays:
			frappe.throw(_("Enter at least one weekday name"))
		self.default_week_off_weekdays = ", ".join(weekdays)
