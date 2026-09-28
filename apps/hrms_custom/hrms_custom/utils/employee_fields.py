"""Employee fields a person may fill themselves (onboarding and later profile updates)."""

import re

import frappe
from frappe.utils import getdate, today

SECTIONS = {
	"personal_details": (
		"first_name",
		"middle_name",
		"last_name",
		"gender",
		"date_of_birth",
		"marital_status",
		"blood_group",
		"nationality",
	),
	"contact_details": ("cell_number", "personal_email", "current_address", "permanent_address"),
	"bank_details": ("account_holder_name", "bank_name", "bank_account_no", "ifsc_code"),
	"emergency_contact": ("emergency_contact_name", "emergency_contact_relation", "emergency_contact_phone"),
}

EDITABLE_FIELDS = tuple(field for fields in SECTIONS.values() for field in fields)

REQUIRED_FIELDS = ("first_name", "date_of_birth", "cell_number")

BANK_FIELDS = SECTIONS["bank_details"]

IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

MARITAL_STATUS_OPTIONS = ("Single", "Married", "Divorced", "Widowed")
BLOOD_GROUP_OPTIONS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")

FIELD_LABELS = {
	"first_name": "First name",
	"middle_name": "Middle name",
	"last_name": "Last name",
	"gender": "Gender",
	"date_of_birth": "Date of birth",
	"marital_status": "Marital status",
	"blood_group": "Blood group",
	"nationality": "Nationality",
	"cell_number": "Mobile number",
	"personal_email": "Personal email",
	"current_address": "Current address",
	"permanent_address": "Permanent address",
	"account_holder_name": "Account holder name",
	"bank_name": "Bank name",
	"bank_account_no": "Account number",
	"ifsc_code": "IFSC code",
	"emergency_contact_name": "Emergency contact name",
	"emergency_contact_relation": "Relation",
	"emergency_contact_phone": "Emergency contact phone",
}


def is_phone(value: str) -> bool:
	return bool(re.fullmatch(r"\+?[\d\s\-()]{10,20}", value)) and len(re.sub(r"\D", "", value)) >= 10


def clean(value):
	if isinstance(value, str):
		value = value.strip()
		return value or None
	return value


def normalize(field: str, value):
	value = clean(value)
	if value is None:
		return None
	text = str(value)
	if field == "ifsc_code":
		return text.upper()
	if field == "bank_account_no":
		return re.sub(r"\s", "", text)
	if field == "personal_email":
		return text.lower()
	if field == "date_of_birth":
		return str(getdate(text))
	return text


def employee_values(employee) -> dict:
	"""`employee` is a name or an object that has the editable fields."""
	if isinstance(employee, str):
		row = frappe.db.get_value("Employee", employee, list(EDITABLE_FIELDS), as_dict=True) or {}
	else:
		row = employee
	return {field: normalize(field, row.get(field)) for field in EDITABLE_FIELDS}


def validate_values(values: dict, *, require_complete: bool = False) -> dict[str, str]:
	"""Validate a merged set of Employee field values. Mutates `values` with normalized forms."""
	errors = {}
	for field in EDITABLE_FIELDS:
		if field in values:
			try:
				values[field] = normalize(field, values[field])
			except Exception:
				errors[field] = f"Enter a valid {FIELD_LABELS.get(field, field).lower()}"
				values[field] = clean(values[field])

	if require_complete or values.get("first_name") is not None:
		if not values.get("first_name"):
			errors["first_name"] = "First name is required"

	dob = values.get("date_of_birth")
	if require_complete or "date_of_birth" in values:
		if not dob:
			errors["date_of_birth"] = "Date of birth is required"
		else:
			try:
				if getdate(dob) >= getdate(today()):
					errors["date_of_birth"] = "Date of birth must be in the past"
			except Exception:
				errors["date_of_birth"] = "Enter a valid date (YYYY-MM-DD)"

	cell = values.get("cell_number")
	if require_complete or "cell_number" in values:
		if not cell:
			errors["cell_number"] = "Mobile number is required"
		elif not is_phone(cell):
			errors["cell_number"] = "Enter a valid mobile number"

	if values.get("personal_email") and "@" not in values["personal_email"]:
		errors["personal_email"] = "Enter a valid email address"

	if values.get("emergency_contact_phone") and not is_phone(values["emergency_contact_phone"]):
		errors["emergency_contact_phone"] = "Enter a valid phone number"

	gender = values.get("gender")
	if gender and not frappe.db.exists("Gender", gender):
		errors["gender"] = "Select a valid gender"

	if values.get("marital_status") and values["marital_status"] not in MARITAL_STATUS_OPTIONS:
		errors["marital_status"] = "Select a valid marital status"

	if values.get("blood_group") and values["blood_group"] not in BLOOD_GROUP_OPTIONS:
		errors["blood_group"] = "Select a valid blood group"

	if any(values.get(f) for f in BANK_FIELDS):
		account_no = values.get("bank_account_no") or ""
		if not re.fullmatch(r"\d{9,18}", account_no):
			errors["bank_account_no"] = "Account number must be 9 to 18 digits"
		ifsc = values.get("ifsc_code") or ""
		if not IFSC_PATTERN.fullmatch(ifsc):
			errors["ifsc_code"] = "Enter a valid 11-character IFSC code"

	return errors


def build_changes(current: dict, proposed: dict) -> tuple[dict, dict[str, str]]:
	"""Return ({field: {from, to}}, {field: error}). Unknown fields are errors."""
	unknown = [key for key in proposed if key not in EDITABLE_FIELDS]
	if unknown:
		return {}, {unknown[0]: f"{unknown[0]} cannot be changed from the app"}

	merged = dict(current)
	merged.update(proposed)
	errors = validate_values(merged)
	if errors:
		return {}, errors

	changes = {}
	for field in proposed:
		before = current.get(field)
		after = merged.get(field)
		if before != after:
			changes[field] = {"from": before, "to": after}
	return changes, {}


def apply_changes(employee_name: str, changes: dict) -> None:
	doc = frappe.get_doc("Employee", employee_name)
	for field, change in changes.items():
		if field not in EDITABLE_FIELDS:
			continue
		doc.set(field, change.get("to"))
	doc.save()


def request_dict(doc) -> dict:
	changes = frappe.parse_json(doc.field_changes) or {}
	return {
		"name": doc.name,
		"employee": doc.employee,
		"employee_name": doc.employee_name,
		"status": doc.status,
		"changes": changes,
		"remarks": doc.remarks,
		"requested_by": doc.requested_by,
		"reviewed_by": doc.reviewed_by,
		"reviewed_on": str(doc.reviewed_on) if doc.reviewed_on else None,
		"creation": str(doc.creation) if doc.creation else None,
		"summary": doc.summary,
	}


def pending_request(employee: str) -> dict | None:
	name = frappe.db.get_value("Profile Update Request", {"employee": employee, "status": "Pending"}, "name")
	if not name:
		return None
	return request_dict(frappe.get_doc("Profile Update Request", name))


def changes_summary(changes: dict) -> str:
	labels = [FIELD_LABELS.get(field, field) for field in changes]
	if not labels:
		return ""
	if len(labels) <= 3:
		return ", ".join(labels)
	return f"{', '.join(labels[:2])} and {len(labels) - 2} more"
