from frappe.model.document import Document


class Company(Document):
	def validate(self):
		self.abbr = (self.abbr or "").strip().upper()
