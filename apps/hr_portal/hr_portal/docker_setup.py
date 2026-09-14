"""Local Docker bootstrap: demo users so /hr can be opened immediately."""

import frappe
from frappe.utils.password import update_password

from hr_portal.constants import HR_ADMIN, HR_EMPLOYEE

DEMO_PASSWORD = "admin"

USERS = (
	{
		"email": "hr.admin@example.com",
		"first_name": "HR",
		"last_name": "Admin",
		"role": HR_ADMIN,
		"employee_name": "HR Admin",
		"must_change_password": 0,
		"department": "HR",
		"designation": "Manager",
	},
	{
		"email": "emp@example.com",
		"first_name": "Demo",
		"last_name": "Employee",
		"role": HR_EMPLOYEE,
		"employee_name": "Demo Employee",
		"must_change_password": 0,
		"department": "Operations",
		"designation": "Associate",
		"bank_account_number": "111122223333",
		"pan_number": "ABCDE1234F",
	},
)


def ensure_dev_users() -> None:
	frappe.set_user("Administrator")
	settings = frappe.get_single("HR Settings")
	if not settings.company_name or settings.company_name == "My Company":
		settings.company_name = "Demo Company"
		settings.enabled = 1
		settings.save(ignore_permissions=True)

	site = _ensure_site()
	shift = _ensure_shift()
	_ensure_leave_type()
	_ensure_vendor()

	for spec in USERS:
		_ensure_user(spec)
		_ensure_employee(spec, site=site, shift=shift)

	frappe.db.commit()


def _ensure_site() -> str:
	existing = frappe.db.get_value("HR Site", {"site_name": "Demo HQ"}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "HR Site",
			"site_name": "Demo HQ",
			"latitude": 19.0760,
			"longitude": 72.8777,
			"radius_meters": 300,
			"address": "Demo office",
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_shift() -> str:
	existing = frappe.db.get_value("HR Shift", {"code": "GEN"}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "HR Shift",
			"shift_name": "General",
			"code": "GEN",
			"start_time": "09:00:00",
			"end_time": "18:00:00",
			"shift_type": "general",
			"status": "Active",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_leave_type() -> None:
	if frappe.db.exists("HR Leave Type", {"code": "CL"}):
		return
	frappe.get_doc(
		{
			"doctype": "HR Leave Type",
			"leave_type_name": "Casual Leave",
			"code": "CL",
			"paid": 1,
			"accrual_per_month": 1,
			"max_balance": 12,
			"status": "Active",
		}
	).insert(ignore_permissions=True)


def _ensure_vendor() -> None:
	if frappe.db.exists("HR Vendor", {"vendor_name": "Demo Staffing"}):
		return
	frappe.get_doc(
		{
			"doctype": "HR Vendor",
			"vendor_name": "Demo Staffing",
			"contact_name": "Vendor Desk",
			"contact_email": "vendor@example.com",
			"status": "Active",
		}
	).insert(ignore_permissions=True)


def _ensure_user(spec: dict) -> None:
	email = spec["email"]
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": spec["first_name"],
				"last_name": spec["last_name"],
				"send_welcome_email": 0,
				"enabled": 1,
				"user_type": "Website User",
			}
		)
		user.insert(ignore_permissions=True)
	user.flags.ignore_permissions = True
	user.add_roles(spec["role"])
	update_password(email, DEMO_PASSWORD)


def _ensure_employee(spec: dict, site: str, shift: str) -> None:
	email = spec["email"]
	existing = frappe.db.get_value("HR Employee", {"user": email}, "name")
	if existing:
		doc = frappe.get_doc("HR Employee", existing)
		changed = False
		if not doc.primary_site:
			doc.primary_site = site
			changed = True
		if not doc.default_shift:
			doc.default_shift = shift
			changed = True
		if not doc.attendance_policy:
			doc.attendance_policy = "geofenced"
			changed = True
		if changed:
			doc.save(ignore_permissions=True)
		return
	frappe.get_doc(
		{
			"doctype": "HR Employee",
			"employee_name": spec["employee_name"],
			"user": email,
			"email": email,
			"phone": "9999900000",
			"portal_role": spec["role"],
			"status": "Active",
			"must_change_password": spec.get("must_change_password", 0),
			"department": spec.get("department"),
			"designation": spec.get("designation"),
			"attendance_policy": "geofenced",
			"primary_site": site,
			"default_shift": shift,
			"bank_account_number": spec.get("bank_account_number"),
			"pan_number": spec.get("pan_number"),
		}
	).insert(ignore_permissions=True)
