from __future__ import annotations

import frappe

from hr_portal.constants import PII_READ_ROLES, SYSTEM_MANAGER
from hr_portal.permissions import get_employee_name, is_staff


PII_FIELDS = (
	"pan_number",
	"aadhaar_number",
	"uan_number",
	"esi_number",
	"pf_account_number",
	"bank_name",
	"bank_ifsc",
	"bank_account_number",
)

EMPLOYEE_FIELDS = (
	"name",
	"employee_code",
	"employee_name",
	"email",
	"phone",
	"status",
	"portal_role",
	"must_change_password",
	"user",
	"employment_type",
	"vendor",
	"date_of_joining",
	"department",
	"designation",
	"reports_to",
	"attendance_policy",
	"primary_site",
	"default_shift",
	"work_shift_start",
	"work_shift_end",
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
	"image",
	*PII_FIELDS,
)

SELF_EDITABLE = (
	"phone",
	"current_address_line_1",
	"current_address_line_2",
	"current_city",
	"current_state",
	"current_pincode",
	"emergency_contact_name",
	"emergency_contact_phone",
	*PII_FIELDS,
)


def can_read_pii(employee_name: str, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	if SYSTEM_MANAGER in roles or roles.intersection(PII_READ_ROLES):
		return True
	return get_employee_name(user) == employee_name


def _hhmm(value) -> str:
	if value is None or value == "":
		return ""
	if hasattr(value, "total_seconds"):
		seconds = int(value.total_seconds()) % (24 * 3600)
		hours, rem = divmod(seconds, 3600)
		minutes, _ = divmod(rem, 60)
		return f"{hours:02d}:{minutes:02d}"
	text = str(value)
	return text[:5] if len(text) >= 5 else text


def employee_to_camel(row: dict, *, include_pii: bool) -> dict:
	manager_name = ""
	if row.get("reports_to"):
		manager_name = frappe.db.get_value("HR Employee", row["reports_to"], "employee_name") or ""

	site_name = ""
	if row.get("primary_site"):
		site_name = frappe.db.get_value("HR Site", row["primary_site"], "site_name") or row["primary_site"]

	payload = {
		"id": row.get("name"),
		"userId": row.get("user") or "",
		"companyId": "default",
		"email": row.get("email") or "",
		"name": row.get("employee_name") or "",
		"role": row.get("portal_role") or "HR Employee",
		"status": (row.get("status") or "Active").lower(),
		"employeeCode": row.get("employee_code") or "",
		"employmentType": row.get("employment_type") or "Permanent",
		"vendorId": row.get("vendor") or "",
		"department": row.get("department") or "",
		"designation": row.get("designation") or "",
		"reportingManagerUserId": row.get("reports_to") or "",
		"dateOfJoining": str(row.get("date_of_joining") or ""),
		"grade": row.get("grade") or "",
		"costCenter": row.get("cost_center") or "",
		"phone": row.get("phone") or "",
		"dateOfBirth": str(row.get("date_of_birth") or ""),
		"gender": row.get("gender") or "",
		"bloodGroup": row.get("blood_group") or "",
		"currentCity": row.get("current_city") or "",
		"currentState": row.get("current_state") or "",
		"currentAddressLine1": row.get("current_address_line_1") or "",
		"currentAddressLine2": row.get("current_address_line_2") or "",
		"currentPincode": row.get("current_pincode") or "",
		"emergencyContactName": row.get("emergency_contact_name") or "",
		"emergencyContactPhone": row.get("emergency_contact_phone") or "",
		"primarySiteId": row.get("primary_site") or "",
		"officeLocation": site_name,
		"attendancePolicy": row.get("attendance_policy") or "geofenced",
		"workShiftStart": _hhmm(row.get("work_shift_start")) or "09:00",
		"workShiftEnd": _hhmm(row.get("work_shift_end")) or "18:00",
		"shiftId": row.get("default_shift") or "",
		"mustChangePassword": bool(row.get("must_change_password")),
		"profilePictureFileId": row.get("image") or "",
	}
	if include_pii:
		payload.update(
			{
				"panNumber": row.get("pan_number") or "",
				"aadhaarNumber": row.get("aadhaar_number") or "",
				"uanNumber": row.get("uan_number") or "",
				"esiNumber": row.get("esi_number") or "",
				"pfAccountNumber": row.get("pf_account_number") or "",
				"bankName": row.get("bank_name") or "",
				"bankIfsc": row.get("bank_ifsc") or "",
				"bankAccountNumber": row.get("bank_account_number") or "",
			}
		)
	else:
		payload.update(
			{
				"panNumber": "",
				"aadhaarNumber": "",
				"uanNumber": "",
				"esiNumber": "",
				"pfAccountNumber": "",
				"bankName": "",
				"bankIfsc": "",
				"bankAccountNumber": "",
			}
		)
	payload["_reportingManager"] = manager_name
	return payload


def load_employee_row(name: str) -> dict:
	row = frappe.db.get_value("HR Employee", name, list(EMPLOYEE_FIELDS), as_dict=True)
	if not row:
		frappe.throw("Employee not found", frappe.DoesNotExistError)
	return row


def staff_or_own(employee_name: str) -> None:
	if is_staff() or frappe.session.user == "Administrator":
		return
	if get_employee_name() != employee_name:
		frappe.throw("Not permitted", frappe.PermissionError)
