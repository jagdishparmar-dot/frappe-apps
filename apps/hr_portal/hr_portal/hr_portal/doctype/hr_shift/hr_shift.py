import frappe
from frappe.model.document import Document
from frappe.utils import get_time


class HRShift(Document):
	def validate(self):
		self.code = (self.code or "").strip().upper()
		if not self.code:
			frappe.throw("Shift code is required")
		if self.start_time and self.end_time:
			start = get_time(self.start_time)
			end = get_time(self.end_time)
			if start == end:
				frappe.throw("Start and end time cannot be the same")
			if not self.crosses_midnight and start > end:
				self.crosses_midnight = 1
				if self.shift_type == "general":
					self.shift_type = "cross_midnight"
