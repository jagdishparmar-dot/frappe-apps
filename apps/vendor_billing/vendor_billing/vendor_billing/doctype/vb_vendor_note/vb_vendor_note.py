from frappe.model.document import Document


class VBVendorNote(Document):
    def before_insert(self):
        if not self.author:
            import frappe

            self.author = frappe.session.user
