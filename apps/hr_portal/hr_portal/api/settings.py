import frappe
from frappe import _
from frappe.utils import cint

from hr_portal.constants import HR_ADMIN, SYSTEM_MANAGER
from hr_portal.utils import newline_list, require_login


SETTINGS_FIELDS = (
	"company_name",
	"legal_name",
	"gstin",
	"timezone",
	"currency",
	"enabled",
	"work_week",
	"late_grace_minutes",
	"contact_email",
	"contact_phone",
	"employee_code_auto_generate",
	"employee_code_prefix",
	"employee_code_padding",
	"employee_code_next_sequence",
	"departments",
	"designations",
	"brand_logo",
	"primary_color",
	"email_sender_name",
	"geofencing",
)

INT_FIELDS = (
	"late_grace_minutes",
	"employee_code_padding",
	"employee_code_next_sequence",
)
CHECK_FIELDS = ("enabled", "employee_code_auto_generate", "geofencing")


@frappe.whitelist()
def get_settings() -> dict:
	require_login()
	doc = frappe.get_single("HR Settings")
	data = {field: doc.get(field) for field in SETTINGS_FIELDS}
	data["department_list"] = newline_list(doc.departments)
	data["designation_list"] = newline_list(doc.designations)
	return data


@frappe.whitelist()
def save_settings(**kwargs) -> dict:
	require_login()
	roles = set(frappe.get_roles())
	if frappe.session.user != "Administrator" and not roles.intersection({HR_ADMIN, SYSTEM_MANAGER}):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_single("HR Settings")
	for key, value in kwargs.items():
		if key not in SETTINGS_FIELDS:
			continue
		if key in INT_FIELDS:
			value = cint(value)
		elif key in CHECK_FIELDS:
			value = 1 if value in (True, 1, "1", "true", "True", "yes", "Yes") else 0
		doc.set(key, value)
	doc.save()
	return get_settings()
