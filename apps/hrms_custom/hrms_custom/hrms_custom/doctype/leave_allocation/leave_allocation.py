import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class LeaveAllocation(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date"))
		if flt(self.allocated) < 0:
			frappe.throw(_("Allocated days cannot be negative"))
		overlapping = frappe.db.sql(
			"""
			select name from `tabLeave Allocation`
			where employee = %s and leave_type = %s and name != %s
				and from_date <= %s and to_date >= %s
			limit 1
			""",
			(self.employee, self.leave_type, self.name or "", self.to_date, self.from_date),
		)
		if overlapping:
			frappe.throw(_("This employee already has an allocation for {0} that overlaps these dates").format(self.leave_type))
