import frappe
from frappe import _
from frappe.utils.password import update_password

from hr_portal.api.serialize import can_read_pii, employee_to_camel, load_employee_row
from hr_portal.constants import HR_ROLES
from hr_portal.permissions import is_staff
from hr_portal.utils import require_employee_write, require_login, split_name


def _clean(value):
	if value is None:
		return None
	if isinstance(value, str):
		text = value.strip()
		return text or None
	return value


@frappe.whitelist()
def get_hire_options() -> dict:
	require_login()
	if not is_staff() and frappe.session.user != "Administrator":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	settings = frappe.get_single("HR Settings")
	from hr_portal.utils import newline_list

	return {
		"departments": newline_list(settings.departments),
		"designations": newline_list(settings.designations),
		"roles": list(HR_ROLES),
		"sites": frappe.get_all(
			"HR Site",
			filters={"status": "Active"},
			fields=["name", "site_name", "latitude", "longitude", "radius_meters"],
			order_by="site_name",
		),
		"shifts": frappe.get_all(
			"HR Shift",
			filters={"status": "Active"},
			fields=["name", "shift_name", "code", "start_time", "end_time"],
			order_by="shift_name",
		),
		"vendors": frappe.get_all(
			"HR Vendor",
			filters={"status": "Active"},
			fields=["name", "vendor_name"],
			order_by="vendor_name",
		),
		"managers": frappe.get_all(
			"HR Employee",
			filters={"status": ["!=", "Inactive"]},
			fields=["name", "employee_name", "employee_code", "portal_role"],
			order_by="employee_name",
		),
	}


@frappe.whitelist()
def get_employee(name: str) -> dict:
	require_login()
	doc = frappe.get_doc("HR Employee", name)
	if not doc.has_permission("read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	row = load_employee_row(doc.name)
	return {"employee": employee_to_camel(row, include_pii=can_read_pii(doc.name)), "name": doc.name}


@frappe.whitelist()
def create_employee(
	employee_name: str,
	email: str,
	password: str,
	phone: str,
	portal_role: str = "HR Employee",
	employment_type: str = "Permanent",
	attendance_policy: str = "geofenced",
	employee_code: str | None = None,
	vendor: str | None = None,
	department: str | None = None,
	designation: str | None = None,
	primary_site: str | None = None,
	default_shift: str | None = None,
	reports_to: str | None = None,
	date_of_joining: str | None = None,
) -> dict:
	require_employee_write()
	employee_name = (employee_name or "").strip()
	email = (email or "").strip().lower()
	phone = (phone or "").strip()
	if len(employee_name) < 2:
		frappe.throw(_("Name is required"))
	if not email or "@" not in email:
		frappe.throw(_("Valid email is required"))
	if not phone or len(phone) < 5:
		frappe.throw(_("Phone is required"))
	if not password or len(password) < 8:
		frappe.throw(_("Password must be at least 8 characters"))
	if portal_role not in HR_ROLES:
		frappe.throw(_("Invalid portal role"))

	if frappe.db.exists("User", email) or frappe.db.exists("HR Employee", {"email": email}):
		frappe.throw(_("A user with this email already exists"))

	active_shifts = frappe.db.count("HR Shift", {"status": "Active"})
	if active_shifts and not _clean(default_shift):
		frappe.throw(_("Shift is required"))

	first, last = split_name(employee_name)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first,
			"last_name": last or first,
			"send_welcome_email": 0,
			"enabled": 1,
			"user_type": "Website User",
		}
	)
	user.flags.ignore_permissions = True
	user.insert()
	update_password(user.name, password)

	emp = frappe.get_doc(
		{
			"doctype": "HR Employee",
			"employee_name": employee_name,
			"employee_code": _clean(employee_code),
			"user": user.name,
			"email": email,
			"phone": phone,
			"portal_role": portal_role,
			"status": "Active",
			"must_change_password": 1,
			"employment_type": employment_type or "Permanent",
			"vendor": _clean(vendor),
			"department": _clean(department),
			"designation": _clean(designation),
			"attendance_policy": attendance_policy or "geofenced",
			"primary_site": _clean(primary_site),
			"default_shift": _clean(default_shift),
			"reports_to": _clean(reports_to),
			"date_of_joining": _clean(date_of_joining),
		}
	)
	try:
		emp.insert()
	except Exception:
		frappe.delete_doc("User", user.name, force=True, ignore_permissions=True)
		raise

	from hr_portal.services.leave_service import seed_leave_balances_for_employee

	seed_leave_balances_for_employee(emp.name)

	row = load_employee_row(emp.name)
	return {"ok": True, "name": emp.name, "employee": employee_to_camel(row, include_pii=can_read_pii(emp.name))}


@frappe.whitelist()
def update_employee(name: str, **kwargs) -> dict:
	require_employee_write()
	doc = frappe.get_doc("HR Employee", name)
	allowed = {
		"employee_name",
		"phone",
		"portal_role",
		"employment_type",
		"vendor",
		"department",
		"designation",
		"attendance_policy",
		"primary_site",
		"default_shift",
		"reports_to",
		"date_of_joining",
		"status",
		"gender",
		"date_of_birth",
		"blood_group",
		"grade",
		"cost_center",
		"current_address_line_1",
		"current_address_line_2",
		"current_city",
		"current_state",
		"current_pincode",
		"emergency_contact_name",
		"emergency_contact_phone",
		"pan_number",
		"aadhaar_number",
		"uan_number",
		"esi_number",
		"pf_account_number",
		"bank_name",
		"bank_ifsc",
		"bank_account_number",
		"work_shift_start",
		"work_shift_end",
	}
	for key, value in kwargs.items():
		if key in allowed:
			doc.set(key, _clean(value) if key != "must_change_password" else value)
	if doc.portal_role and doc.portal_role not in HR_ROLES:
		frappe.throw(_("Invalid portal role"))
	doc.save()
	row = load_employee_row(doc.name)
	return {"ok": True, "name": doc.name, "employee": employee_to_camel(row, include_pii=can_read_pii(doc.name))}


@frappe.whitelist()
def set_employee_status(name: str, status: str) -> dict:
	require_employee_write()
	if status not in ("Active", "Inactive", "Invited"):
		frappe.throw(_("Invalid status"))
	doc = frappe.get_doc("HR Employee", name)
	doc.status = status
	doc.save()
	return {"ok": True, "status": doc.status}


@frappe.whitelist()
def reset_employee_password(name: str, new_password: str) -> dict:
	require_employee_write()
	if not new_password or len(new_password) < 8:
		frappe.throw(_("Password must be at least 8 characters"))
	doc = frappe.get_doc("HR Employee", name)
	if not doc.user:
		frappe.throw(_("Employee has no login user"))
	update_password(doc.user, new_password)
	doc.must_change_password = 1
	doc.save()
	return {"ok": True}
