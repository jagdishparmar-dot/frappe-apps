"""Employee profile and HR-approved updates (spec section 6)."""

import json

import frappe

from hrms_custom.api.onboarding import get_hr_recipients
from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import get_session_employee
from hrms_custom.hrms_custom.doctype.profile_update_request.profile_update_request import (
	REVIEWED_STATUSES,
)
from hrms_custom.permissions import is_hr
from hrms_custom.utils.employee_fields import (
	BLOOD_GROUP_OPTIONS,
	EDITABLE_FIELDS,
	MARITAL_STATUS_OPTIONS,
	SECTIONS,
	build_changes,
	employee_values,
	pending_request,
	request_dict,
)
from hrms_custom.utils.notify import try_sendmail
from hrms_custom.utils.profile_image import (
	clear_profile_image,
	profile_image_response,
	read_uploaded_image,
	save_profile_image,
)

PROFILE_FIELDS = (
	"name",
	"employee_name",
	"first_name",
	"last_name",
	"gender",
	"date_of_birth",
	"date_of_joining",
	"company",
	"department",
	"designation",
	"branch",
	"reports_to",
	"cell_number",
	"company_email",
	"personal_email",
	"image",
	"status",
	"onboarding_status",
	"employee_type",
	"vendor",
	"other_employee_type",
	"user_id",
)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_my_profile():
	"""Profile of the logged-in employee. The mobile app also uses this as its session check, and
	routes invited joiners to onboarding based on `onboarding_status`."""
	fields = tuple(dict.fromkeys([*PROFILE_FIELDS, *EDITABLE_FIELDS]))
	profile = get_session_employee(fields, allow_onboarding=True)
	values = employee_values(profile)
	profile["roles"] = frappe.get_roles()
	profile["values"] = values
	profile["sections"] = {section: {f: values.get(f) for f in fields} for section, fields in SECTIONS.items()}
	profile["pending_request"] = pending_request(profile.name)
	profile["genders"] = frappe.get_all("Gender", pluck="name", order_by="name asc")
	profile["marital_status_options"] = list(MARITAL_STATUS_OPTIONS)
	profile["blood_group_options"] = list(BLOOD_GROUP_OPTIONS)
	profile["has_image"] = bool(profile.get("image"))
	return profile


@frappe.whitelist(methods=["POST"])
@api_endpoint
def upload_profile_image():
	"""Employee: multipart upload (`file` part). Replaces the current photo immediately."""
	employee = get_session_employee(("name", "image"), allow_onboarding=True)
	filename, content = read_uploaded_image()
	file_url = save_profile_image(employee.name, filename, content)
	return success({"image": file_url, "has_image": True}, "Profile photo updated")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def remove_profile_image():
	"""Employee: clear their own photo."""
	employee = get_session_employee(("name", "image"), allow_onboarding=True)
	if not employee.image:
		raise ApiError("No profile photo uploaded", 404)
	clear_profile_image(employee.name)
	return success({"image": None, "has_image": False}, "Profile photo removed")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_profile_image():
	"""The photo bytes for the logged-in employee. Private files are never served from a public URL."""
	employee = get_session_employee(("name", "image"), allow_onboarding=True)
	return profile_image_response(employee.name, employee.image)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def request_profile_update(changes=None):
	"""Employee: submit a diff of editable fields. HR must approve before Employee is written."""
	employee = get_session_employee(("name", "employee_name"))
	proposed = _parse_changes(changes)
	if pending_request(employee.name):
		raise ApiError("You already have a profile update waiting for HR. Cancel it or wait.", 409)

	current = employee_values(employee.name)
	diff, errors = build_changes(current, proposed)
	if errors:
		raise ApiError("Please correct the highlighted fields", 400, {"errors": errors})
	if not diff:
		raise ApiError("No changes to submit", 400)

	doc = frappe.get_doc(
		{
			"doctype": "Profile Update Request",
			"employee": employee.name,
			"status": "Pending",
			"field_changes": diff,
			"requested_by": frappe.session.user,
		}
	).insert()
	_notify_hr(employee, doc)
	return success(request_dict(doc), "Submitted — pending HR approval")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def cancel_profile_update(request=None):
	"""Employee: withdraw their own pending request."""
	employee = get_session_employee(("name",)).name
	doc = _get_request(request)
	if doc.employee != employee:
		raise ApiError("Profile update not found", 404)
	if doc.status != "Pending":
		raise ApiError("Only a pending request can be cancelled", 409)
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)
	return success(request_dict(doc), "Profile update cancelled")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_profile_update(request=None, status=None, remarks=None):
	"""HR: approve (applies the diff to Employee) or reject. Rejection needs remarks."""
	if not is_hr():
		raise ApiError("Only HR can review profile updates", 403)
	if status not in REVIEWED_STATUSES:
		raise ApiError("Status must be Approved or Rejected", 400)
	doc = _get_request(request)
	if doc.status == status and (status == "Approved" or (doc.remarks or "") == (remarks or "")):
		return success(request_dict(doc), f"Already {status.lower()}")
	if doc.status != "Pending":
		raise ApiError(f"This request is already {doc.status.lower()}", 409)
	doc.status = status
	if remarks is not None:
		doc.remarks = remarks
	doc.save()
	verb = "approved" if status == "Approved" else "rejected"
	return success(request_dict(doc), f"Profile update {verb}")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_profile_updates(employee=None, status=None):
	"""Pending (or filtered) profile updates. Employees see only their own."""
	filters = {}
	if status:
		filters["status"] = status
	if is_hr():
		if employee:
			filters["employee"] = employee
	else:
		own = get_session_employee(("name",)).name
		if employee and employee != own:
			raise ApiError("You can only view your own profile updates", 403)
		filters["employee"] = own

	rows = frappe.get_all(
		"Profile Update Request",
		filters=filters,
		fields=[
			"name",
			"employee",
			"employee_name",
			"status",
			"summary",
			"remarks",
			"requested_by",
			"reviewed_by",
			"reviewed_on",
			"creation",
			"field_changes",
		],
		order_by="creation desc",
		limit=100,
	)
	for row in rows:
		row["changes"] = frappe.parse_json(row.pop("field_changes", None)) or {}
		row["reviewed_on"] = str(row["reviewed_on"]) if row.get("reviewed_on") else None
		row["creation"] = str(row["creation"]) if row.get("creation") else None
	return {"employee": filters.get("employee"), "requests": rows}


def _parse_changes(changes) -> dict:
	if changes in (None, ""):
		raise ApiError("Send the fields you want to change", 400)
	if isinstance(changes, str):
		try:
			changes = json.loads(changes)
		except ValueError as e:
			raise ApiError("changes must be a JSON object", 400) from e
	if not isinstance(changes, dict):
		raise ApiError("changes must be a JSON object", 400)
	return changes


def _get_request(name):
	if not name or not frappe.db.exists("Profile Update Request", name):
		raise ApiError("Profile update not found", 404)
	return frappe.get_doc("Profile Update Request", name)


def _notify_hr(employee, request_doc) -> None:
	recipients = get_hr_recipients()
	if not recipients:
		return
	from frappe.utils import escape_html, get_url

	link = get_url(f"/desk/profile-update-request/{request_doc.name}")
	try_sendmail(
		recipients=recipients,
		subject=f"Profile update: {employee.employee_name}",
		message=(
			f"<p><b>{escape_html(employee.employee_name)}</b> ({employee.name}) submitted a profile "
			f"update ({escape_html(request_doc.summary)}).</p>"
			f'<p><a href="{link}">Review the request</a></p>'
		),
		reference_doctype="Profile Update Request",
		reference_name=request_doc.name,
	)
