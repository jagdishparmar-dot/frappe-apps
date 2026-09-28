import frappe
from frappe.model.document import Document


class Department(Document):
	def autoname(self):
		# Same department name can exist in several companies: "Engineering - ACME".
		abbr = frappe.db.get_value("Company", self.company, "abbr")
		self.name = f"{self.department_name.strip()} - {abbr}"
