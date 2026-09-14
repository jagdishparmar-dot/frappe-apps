import frappe
from frappe.model.document import Document


class HRSite(Document):
	def validate(self):
		if self.latitude is None or self.latitude < -90 or self.latitude > 90:
			frappe.throw("Latitude must be between -90 and 90")
		if self.longitude is None or self.longitude < -180 or self.longitude > 180:
			frappe.throw("Longitude must be between -180 and 180")
		radius = int(self.radius_meters or 0)
		if radius < 20 or radius > 50000:
			frappe.throw("Radius must be between 20 and 50,000 meters")
