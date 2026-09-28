import frappe
from frappe import _
from frappe.model.document import Document


class GeofenceLocation(Document):
	def validate(self):
		if not -90 <= self.latitude <= 90:
			frappe.throw(_("Latitude must be between -90 and 90"))
		if not -180 <= self.longitude <= 180:
			frappe.throw(_("Longitude must be between -180 and 180"))
		if self.radius_meters <= 0:
			frappe.throw(_("Radius must be greater than zero"))
