import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeGeofenceMap(Document):
	def validate(self):
		self.validate_unique_mapping()
		self.validate_company()

	def validate_unique_mapping(self):
		duplicate = frappe.db.exists(
			"Employee Geofence Map",
			{
				"employee": self.employee,
				"geofence_location": self.geofence_location,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("Employee {0} is already mapped to {1}").format(self.employee, self.geofence_location),
				frappe.DuplicateEntryError,
			)

	def validate_company(self):
		location_company = frappe.db.get_value("Geofence Location", self.geofence_location, "company")
		employee_company = frappe.db.get_value("Employee", self.employee, "company")
		if location_company != employee_company:
			frappe.throw(
				_("Geofence Location {0} belongs to {1}, but the employee belongs to {2}").format(
					self.geofence_location, location_company, employee_company
				)
			)
