import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

EMPLOYEE_ROLE = "Employee"


class Employee(Document):
	def validate(self):
		self.employee_name = " ".join(
			part.strip() for part in (self.first_name, self.middle_name, self.last_name) if part and part.strip()
		)
		self.validate_dates()
		self.validate_reports_to()
		self.validate_department_company()
		self.validate_employee_type()
		if self.ifsc_code:
			self.ifsc_code = self.ifsc_code.strip().upper()

	def after_insert(self):
		from hrms_custom.utils.employee_defaults import apply_company_defaults

		apply_company_defaults(self, is_new=True)

	def on_update(self):
		if self.has_value_changed("company"):
			from hrms_custom.utils.employee_defaults import apply_company_defaults

			apply_company_defaults(self, is_new=False)
		if self.user_id:
			self.grant_employee_role()

	def validate_dates(self):
		if not self.date_of_birth and self.requires_personal_details():
			frappe.throw(_("Date of Birth is required"), frappe.MandatoryError)
		if self.date_of_birth and getdate(self.date_of_birth) >= getdate():
			frappe.throw(_("Date of Birth must be in the past"))
		if self.date_of_birth and self.date_of_joining and getdate(self.date_of_joining) <= getdate(
			self.date_of_birth
		):
			frappe.throw(_("Date of Joining must be after Date of Birth"))
		if self.relieving_date and getdate(self.relieving_date) < getdate(self.date_of_joining):
			frappe.throw(_("Relieving Date cannot be before Date of Joining"))

	def requires_personal_details(self) -> bool:
		"""HR may create a bare Inactive record and let the joiner fill the rest during onboarding."""
		return self.status == "Active" or self.onboarding_status in ("Pending Verification", "Verified")

	def validate_reports_to(self):
		if self.reports_to and self.reports_to == self.name:
			frappe.throw(_("An employee cannot report to themselves"))

	def validate_department_company(self):
		if not self.department:
			return
		department_company = frappe.db.get_value("Department", self.department, "company")
		if department_company != self.company:
			frappe.throw(
				_("Department {0} belongs to {1}, not {2}").format(
					self.department, department_company, self.company
				)
			)

	def validate_employee_type(self):
		self.employee_type = self.employee_type or "Permanent"
		if self.employee_type == "Contract":
			if not self.vendor:
				frappe.throw(_("Vendor is required for contract / 3PL employees"))
			if not frappe.db.exists("Vendor", self.vendor):
				frappe.throw(_("Unknown vendor"))
			self.other_employee_type = None
			return
		self.vendor = None
		if self.employee_type == "Other":
			label = (self.other_employee_type or "").strip()
			if not label:
				frappe.throw(_("Specify the other employee type"))
			self.other_employee_type = label
			return
		self.other_employee_type = None

	def grant_employee_role(self):
		user = frappe.get_doc("User", self.user_id)
		if EMPLOYEE_ROLE not in {r.role for r in user.roles}:
			user.flags.ignore_permissions = True
			user.add_roles(EMPLOYEE_ROLE)
