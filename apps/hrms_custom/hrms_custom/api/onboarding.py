"""Employee self-onboarding (spec section 5).

Flow: HR creates an Inactive Employee and calls `invite_employee` -> the joiner logs into the app with
OTP, uploads documents and calls `submit_onboarding_form` -> HR is notified and an Onboarding
Checklist is created -> HR verifies and activates the employee.
"""

import json
import re

import frappe
from frappe.utils import add_days, escape_html, get_url, getdate, now_datetime, today

from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import get_session_employee
from hrms_custom.permissions import is_hr
from hrms_custom.utils.documents import (
	DOCUMENT_TYPES,
	MAX_UPLOAD_BYTES,  # noqa: F401 (re-exported for tests)
	delete_employee_document,
	list_employee_documents,
	read_request_file,
	save_employee_document,
)
from hrms_custom.utils.employee_fields import IFSC_PATTERN, SECTIONS, is_phone
from hrms_custom.utils.notify import try_sendmail

HR_NOTIFY_ROLES = ("HR Admin", "HR Executive")

STATUS_INVITED = "Invited"
STATUS_PENDING = "Pending Verification"

ID_DOCUMENT_TYPE = "ID Proof"

DEFAULT_CHECKLIST_TASKS = (
	("Verify personal details and documents", 2),
	("Assign work location (geofence) and shift", 3),
	("Activate employee record", 3),
)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def invite_employee(employee=None):
	"""HR: create the joiner's login and allow them to fill the onboarding form in the mobile app."""
	if not is_hr():
		raise ApiError("Only HR can invite employees", 403)
	if not employee or not frappe.db.exists("Employee", employee):
		raise ApiError("Employee not found", 404)

	doc = frappe.get_doc("Employee", employee)
	if doc.onboarding_status in (STATUS_PENDING, "Verified"):
		raise ApiError(f"This employee's onboarding is already {doc.onboarding_status.lower()}", 409)
	if doc.status == "Active" and not doc.onboarding_status:
		raise ApiError("This employee is already active", 409)

	email = (doc.personal_email or doc.company_email or "").strip().lower()
	if not email:
		raise ApiError("Add a personal or company email before inviting", 400)

	if not doc.user_id:
		doc.user_id = _get_or_create_user(email, doc)
	doc.status = "Inactive"
	doc.onboarding_status = STATUS_INVITED
	doc.save(ignore_permissions=True)

	emailed = _send_invite(doc, email)
	login_hint = doc.cell_number or email
	message = (
		f"Invitation sent to {email}"
		if emailed
		else f"Invite created, but the email could not be sent (set up an outgoing Email Account). "
		f"The joiner can sign in to the app with {login_hint}."
	)
	return success(
		{
			"employee": doc.name,
			"user": doc.user_id,
			"onboarding_status": doc.onboarding_status,
			"email_sent": emailed,
		},
		message,
	)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def get_onboarding_form():
	"""Joiner: current form values (pre-filled by HR), uploaded documents and status."""
	employee = get_session_employee(("name", "employee_name", "company"), allow_onboarding=True)
	values = frappe.db.get_value(
		"Employee", employee.name, [f for fields in SECTIONS.values() for f in fields], as_dict=True
	)
	return {
		"employee": employee.name,
		"company": employee.company,
		"onboarding_status": employee.onboarding_status,
		"sections": {section: {f: values.get(f) for f in fields} for section, fields in SECTIONS.items()},
		"documents": list_employee_documents(employee.name),
		"document_types": list(DOCUMENT_TYPES),
		"genders": frappe.get_all("Gender", pluck="name", order_by="name asc"),
	}


@frappe.whitelist(methods=["POST"])
@api_endpoint
def upload_onboarding_document(document_type=None):
	"""Joiner: multipart upload (`file` part) of one document, attached privately to the Employee."""
	employee = _get_editable_joiner()
	filename, content = read_request_file()
	return success(save_onboarding_document(employee, document_type, filename, content), "Document uploaded")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def delete_onboarding_document(document=None):
	"""Joiner: remove a document uploaded by mistake (only before the form is submitted)."""
	employee = _get_editable_joiner()
	owner = frappe.db.get_value("Employee Document", document, "employee") if document else None
	if owner != employee:
		raise ApiError("Document not found", 404)
	delete_employee_document(document)
	return success({"document": document}, "Document removed")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def submit_onboarding_form(
	personal_details=None, contact_details=None, bank_details=None, emergency_contact=None, documents=None
):
	"""Joiner: validate and save the form, mark it Pending Verification, notify HR, create the checklist."""
	employee = get_session_employee(("name", "employee_name", "company"), allow_onboarding=True)
	if employee.onboarding_status == STATUS_PENDING:
		raise ApiError("You have already submitted your details. HR is reviewing them.", 409)
	if employee.onboarding_status != STATUS_INVITED:
		raise ApiError("Onboarding is not open for your account", 403)

	payload = {
		"personal_details": personal_details,
		"contact_details": contact_details,
		"bank_details": bank_details,
		"emergency_contact": emergency_contact,
	}
	values = {}
	for section, fields in SECTIONS.items():
		data = _parse_json_object(payload[section], section)
		values.update({f: _clean(data.get(f)) for f in fields if f in data})

	document_names = _parse_json_list(documents, "documents")
	errors = validate_submission(values, employee.name, document_names)
	if errors:
		raise ApiError("Please fix the highlighted fields", 400, {"errors": errors})

	doc = frappe.get_doc("Employee", employee.name)
	doc.update(values)
	doc.onboarding_status = STATUS_PENDING
	doc.onboarding_submitted_on = now_datetime()
	doc.save(ignore_permissions=True)

	checklist = _ensure_checklist(doc)
	_notify_hr(doc, checklist)
	return success(
		{"onboarding_status": doc.onboarding_status, "checklist": checklist},
		"Submitted — pending verification",
	)


def validate_submission(values: dict, employee: str, document_names: list[str]) -> dict[str, str]:
	"""Return {field: message}. Required by spec: name, DOB, phone and at least one ID document."""
	errors = {}
	if not values.get("first_name"):
		errors["first_name"] = "First name is required"

	dob = values.get("date_of_birth")
	if not dob:
		errors["date_of_birth"] = "Date of birth is required"
	else:
		try:
			if getdate(dob) >= getdate(today()):
				errors["date_of_birth"] = "Date of birth must be in the past"
		except Exception:
			errors["date_of_birth"] = "Enter a valid date (YYYY-MM-DD)"

	if not values.get("cell_number"):
		errors["cell_number"] = "Mobile number is required"
	elif not is_phone(values["cell_number"]):
		errors["cell_number"] = "Enter a valid mobile number"

	if values.get("emergency_contact_phone") and not is_phone(values["emergency_contact_phone"]):
		errors["emergency_contact_phone"] = "Enter a valid phone number"

	gender = values.get("gender")
	if gender and not frappe.db.exists("Gender", gender):
		errors["gender"] = "Select a valid gender"

	if any(values.get(f) for f in SECTIONS["bank_details"]):
		account_no = re.sub(r"\s", "", values.get("bank_account_no") or "")
		if not re.fullmatch(r"\d{9,18}", account_no):
			errors["bank_account_no"] = "Account number must be 9 to 18 digits"
		else:
			values["bank_account_no"] = account_no
		ifsc = (values.get("ifsc_code") or "").upper()
		if not IFSC_PATTERN.fullmatch(ifsc):
			errors["ifsc_code"] = "Enter a valid 11-character IFSC code"
		else:
			values["ifsc_code"] = ifsc

	owned = frappe.get_all(
		"Employee Document",
		filters={"name": ("in", document_names or [""]), "employee": employee},
		fields=["name", "document_type"],
	)
	if len(owned) != len(set(document_names)):
		errors["documents"] = "Some documents could not be found. Please re-upload them."
	elif not any(d.document_type == ID_DOCUMENT_TYPE for d in owned):
		errors["documents"] = "Upload at least one ID proof"

	return errors


def save_onboarding_document(employee: str, document_type: str | None, filename: str, content: bytes) -> dict:
	return save_employee_document(employee, document_type, filename, content)


def _get_editable_joiner() -> str:
	employee = get_session_employee(("name",), allow_onboarding=True)
	if employee.onboarding_status != STATUS_INVITED:
		raise ApiError("Documents can no longer be changed after submitting", 403)
	return employee.name


def _ensure_checklist(employee_doc) -> str:
	existing = frappe.db.get_value("Onboarding Checklist", {"employee": employee_doc.name}, "name")
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Onboarding Checklist",
				"employee": employee_doc.name,
				"date_of_joining": employee_doc.date_of_joining,
				"tasks": [
					{"task_name": task, "due_date": add_days(today(), days), "status": "Pending"}
					for task, days in DEFAULT_CHECKLIST_TASKS
				],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def get_hr_recipients() -> list[str]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": ("in", HR_NOTIFY_ROLES), "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	users = [u for u in users if u not in ("Administrator", "Guest")]
	return frappe.get_all("User", filters={"name": ("in", users or [""]), "enabled": 1}, pluck="email")


def _notify_hr(employee_doc, checklist: str) -> None:
	recipients = get_hr_recipients()
	if not recipients:
		frappe.log_error(
			title="hrms_custom: no HR recipients for onboarding notification",
			message=f"Employee {employee_doc.name} submitted onboarding but no user has an HR role.",
		)
		return
	link = get_url(f"/desk/employee/{employee_doc.name}")
	try_sendmail(
		recipients=recipients,
		subject=f"Onboarding submitted: {employee_doc.employee_name}",
		message=(
			f"<p><b>{escape_html(employee_doc.employee_name)}</b> ({employee_doc.name}) has submitted "
			f"their onboarding details and documents for verification.</p>"
			f'<p><a href="{link}">Review the employee record</a> · Checklist: {checklist}</p>'
		),
		reference_doctype="Employee",
		reference_name=employee_doc.name,
	)


def _send_invite(employee_doc, email: str) -> bool:
	company = escape_html(employee_doc.company)
	login_hint = escape_html(employee_doc.cell_number or email)
	return try_sendmail(
		recipients=[email],
		subject=f"Welcome to {employee_doc.company} — complete your onboarding",
		message=(
			f"<p>Hi {escape_html(employee_doc.first_name)},</p>"
			f"<p>Welcome to {company}! Please install the HRMS mobile app and sign in with "
			f"<b>{login_hint}</b>. You will receive a one-time code to log in, then you can fill in "
			f"your details and upload your documents.</p>"
		),
		reference_doctype="Employee",
		reference_name=employee_doc.name,
	)


def _get_or_create_user(email: str, employee_doc) -> str:
	if frappe.db.exists("User", email):
		linked = frappe.db.get_value("Employee", {"user_id": email, "name": ("!=", employee_doc.name)}, "name")
		if linked:
			raise ApiError(f"User {email} is already linked to employee {linked}", 409)
		return email
	return (
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": employee_doc.first_name,
				"last_name": employee_doc.last_name,
				"mobile_no": employee_doc.cell_number,
				"send_welcome_email": 0,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _parse_json_object(value, label: str) -> dict:
	if value in (None, ""):
		return {}
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError as e:
			raise ApiError(f"{label} must be a JSON object", 400) from e
	if not isinstance(value, dict):
		raise ApiError(f"{label} must be a JSON object", 400)
	return value


def _parse_json_list(value, label: str) -> list[str]:
	if value in (None, ""):
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError as e:
			raise ApiError(f"{label} must be a list", 400) from e
	if not isinstance(value, list):
		raise ApiError(f"{label} must be a list", 400)
	return [str(v) for v in value]


def _clean(value):
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return value


