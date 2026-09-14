import frappe
from frappe import _

from hr_portal.api.documents import list_documents
from hr_portal.api.serialize import (
	SELF_EDITABLE,
	can_read_pii,
	employee_to_camel,
	load_employee_row,
)
from hr_portal.permissions import get_employee_name
from hr_portal.utils import require_login


def _own_employee() -> str:
	require_login()
	name = get_employee_name()
	if not name:
		frappe.throw(_("No employee record found"))
	return name


def _geofence_context(row: dict) -> dict:
	lat = 19.077
	lon = 72.998
	radius = 500
	location = "Unassigned site"
	if row.get("primary_site"):
		site = frappe.db.get_value(
			"HR Site",
			row["primary_site"],
			["site_name", "latitude", "longitude", "radius_meters"],
			as_dict=True,
		)
		if site:
			location = site.site_name or location
			lat = float(site.latitude or lat)
			lon = float(site.longitude or lon)
			radius = int(site.radius_meters or radius)
	return {
		"officeLocation": location,
		"officeLatitude": lat,
		"officeLongitude": lon,
		"geofenceRadiusMeters": radius,
	}


def profile_snapshot(employee_name: str | None = None) -> dict:
	name = employee_name or _own_employee()
	row = load_employee_row(name)
	employee = employee_to_camel(row, include_pii=can_read_pii(name))
	employee.update(_geofence_context(row))
	picture = ""
	docs = list_documents(name)
	profile_docs = [d for d in docs if d["category"] == "profile_picture"]
	if profile_docs:
		picture = profile_docs[0]["previewUrl"]
	elif row.get("image"):
		picture = row["image"]
		if picture.startswith("/"):
			picture = frappe.utils.get_url(picture)
	return {
		"ok": True,
		"employee": employee,
		"reportingManager": employee.pop("_reportingManager", ""),
		"profilePictureUrl": picture,
		"documents": docs,
	}


@frappe.whitelist()
def get_profile() -> dict:
	return profile_snapshot()


@frappe.whitelist()
def update_profile(**kwargs) -> dict:
	"""ESS self-update. Allowlisted fields only; includes own statutory/bank (existing product)."""
	name = _own_employee()
	doc = frappe.get_doc("HR Employee", name)
	camel_to_snake = {
		"phone": "phone",
		"currentAddressLine1": "current_address_line_1",
		"currentAddressLine2": "current_address_line_2",
		"currentCity": "current_city",
		"currentState": "current_state",
		"currentPincode": "current_pincode",
		"emergencyContactName": "emergency_contact_name",
		"emergencyContactPhone": "emergency_contact_phone",
		"panNumber": "pan_number",
		"aadhaarNumber": "aadhaar_number",
		"uanNumber": "uan_number",
		"esiNumber": "esi_number",
		"pfAccountNumber": "pf_account_number",
		"bankName": "bank_name",
		"bankIfsc": "bank_ifsc",
		"bankAccountNumber": "bank_account_number",
	}
	dirty = False
	for key, value in kwargs.items():
		field = camel_to_snake.get(key, key if key in SELF_EDITABLE else None)
		if not field or field not in SELF_EDITABLE:
			continue
		if isinstance(value, str):
			value = value.strip()
		doc.set(field, value)
		dirty = True
	if not dirty:
		frappe.throw(_("No valid fields to update"))
	doc.flags.ignore_permissions = True
	doc.save()
	return profile_snapshot(name)
