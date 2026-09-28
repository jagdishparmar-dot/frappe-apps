import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime


class EmployeeCheckin(Document):
	def before_validate(self):
		self.time = get_datetime(self.time).replace(microsecond=0)

	def validate(self):
		self.validate_active_employee()
		self.validate_duplicate_log()

	def validate_active_employee(self):
		if frappe.db.get_value("Employee", self.employee, "status") != "Active":
			frappe.throw(_("Employee {0} is not active").format(self.employee))

	def validate_duplicate_log(self):
		duplicate = frappe.db.exists(
			"Employee Checkin",
			{
				"employee": self.employee,
				"time": self.time,
				"log_type": self.log_type,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(_("This employee already has a {0} log at this time").format(self.log_type))
