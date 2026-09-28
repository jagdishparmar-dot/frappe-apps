import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_time

from hrms_custom.utils.shifts import shift_duration_hours, times_are_overnight


class ShiftType(Document):
	def validate(self):
		if (self.grace_minutes or 0) < 0:
			frappe.throw(_("Late coming grace minutes cannot be negative"))
		if (self.early_exit_grace_minutes or 0) < 0:
			frappe.throw(_("Early going grace minutes cannot be negative"))
		for field, label in (
			("working_hours", _("Working hours")),
			("minimum_hours_present", _("Minimum hours for Present")),
			("minimum_hours_half_day", _("Minimum hours for Half Day")),
		):
			if flt(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative").format(label))
		self.start_time = get_time(self.start_time)
		self.end_time = get_time(self.end_time)
		self.is_overnight = 1 if times_are_overnight(self.start_time, self.end_time) else 0
		if not flt(self.working_hours):
			self.working_hours = shift_duration_hours(self.start_time, self.end_time)
		present = flt(self.minimum_hours_present)
		half = flt(self.minimum_hours_half_day)
		working = flt(self.working_hours)
		if half and present and half > present:
			frappe.throw(_("Minimum hours for Half Day cannot exceed minimum hours for Present"))
		if present and working and present > working:
			frappe.throw(_("Minimum hours for Present cannot exceed working hours"))
