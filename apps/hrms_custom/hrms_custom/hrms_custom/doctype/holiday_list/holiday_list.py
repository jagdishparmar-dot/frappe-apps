import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class HolidayList(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date"))
		seen = set()
		for row in self.holidays:
			day = getdate(row.holiday_date)
			if day in seen:
				frappe.throw(_("Holiday {0} is listed more than once").format(day))
			seen.add(day)
			if day < getdate(self.from_date) or day > getdate(self.to_date):
				frappe.throw(_("Holiday {0} is outside {1} – {2}").format(day, self.from_date, self.to_date))
