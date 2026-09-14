import frappe
from frappe.model.document import Document
from frappe.utils import get_time

from hr_portal.constants import HR_ROLES
from hr_portal.utils import newline_list


def _hhmm(value) -> str:
	t = get_time(value)
	return f"{t.hour:02d}:{t.minute:02d}"


class HREmployee(Document):
	def before_naming(self):
		self.ensure_employee_code()

	def validate(self):
		self.email = (self.email or "").strip().lower()
		if self.user and not self.email:
			self.email = frappe.db.get_value("User", self.user, "email") or self.email
		self._validate_user_unique()
		self._validate_reports_to()
		self._validate_employment()
		self._validate_attendance()
		self._sync_shift_times()
		self._validate_catalog_values()

	def on_update(self):
		self.sync_user_role()
		self.sync_user_enabled()

	def after_insert(self):
		self.sync_user_role()
		self.sync_user_enabled()

	def ensure_employee_code(self):
		if self.employee_code:
			self.employee_code = self.employee_code.strip().upper()
			return
		settings = frappe.get_single("HR Settings")
		if not settings.employee_code_auto_generate:
			frappe.throw("Employee Code is required")
		prefix = (settings.employee_code_prefix or "EMP").strip()
		padding = int(settings.employee_code_padding or 4)
		seq = int(settings.employee_code_next_sequence or 1)
		code = f"{prefix}{str(seq).zfill(padding)}"
		while frappe.db.exists("HR Employee", {"employee_code": code}):
			seq += 1
			code = f"{prefix}{str(seq).zfill(padding)}"
		self.employee_code = code
		frappe.db.set_single_value("HR Settings", "employee_code_next_sequence", seq + 1)

	def _validate_user_unique(self):
		if not self.user:
			return
		existing = frappe.db.get_value("HR Employee", {"user": self.user, "name": ["!=", self.name or ""]}, "name")
		if existing:
			frappe.throw(f"User {self.user} is already linked to {existing}")

	def _validate_reports_to(self):
		if self.reports_to and self.reports_to == self.name:
			frappe.throw("An employee cannot report to themselves")

	def _validate_employment(self):
		if self.employment_type == "3PL" and not self.vendor:
			frappe.throw("3PL manpower provider is required for 3PL employees")

	def _validate_attendance(self):
		policy = self.attendance_policy or "geofenced"
		if policy == "geofenced" and not self.primary_site:
			frappe.throw("Primary site is required for geofenced attendance")

	def _sync_shift_times(self):
		if not self.default_shift:
			return
		start, end = frappe.db.get_value("HR Shift", self.default_shift, ["start_time", "end_time"]) or (None, None)
		if start and not self.work_shift_start:
			self.work_shift_start = _hhmm(start)
		if end and not self.work_shift_end:
			self.work_shift_end = _hhmm(end)

	def _validate_catalog_values(self):
		settings = frappe.get_single("HR Settings")
		departments = newline_list(settings.departments)
		designations = newline_list(settings.designations)
		if self.department and departments and self.department not in departments:
			frappe.throw("Department must be selected from HR Settings")
		if self.designation and designations and self.designation not in designations:
			frappe.throw("Designation must be selected from HR Settings")

	def sync_user_role(self):
		if not self.user or self.portal_role not in HR_ROLES:
			return
		user = frappe.get_doc("User", self.user)
		user.flags.ignore_permissions = True
		user.add_roles(self.portal_role)
		for role in HR_ROLES:
			if role != self.portal_role:
				user.remove_roles(role)

	def sync_user_enabled(self):
		if not self.user:
			return
		enabled = 0 if self.status == "Inactive" else 1
		current = frappe.db.get_value("User", self.user, "enabled")
		if int(current or 0) != enabled:
			frappe.db.set_value("User", self.user, "enabled", enabled)
