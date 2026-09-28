import json

import frappe
from frappe.utils import add_years, getdate

TEST_COMPANY = "_Test HRMS Company"


def call(endpoint, **kwargs) -> tuple[int, dict]:
	"""Invoke an `api_endpoint`-wrapped method and return (http_status, envelope)."""
	response = endpoint(**kwargs)
	return response.status_code, json.loads(response.get_data(as_text=True))


def get_test_company() -> str:
	if not frappe.db.exists("Company", TEST_COMPANY):
		frappe.get_doc({"doctype": "Company", "company_name": TEST_COMPANY, "abbr": "_THC"}).insert(
			ignore_permissions=True
		)
	return TEST_COMPANY


def make_employee_user(email: str, company: str, first_name: str, mobile: str | None = None) -> str:
	"""Create (or reuse) an enabled User linked to an active Employee (which grants the Employee role)."""
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": first_name, "send_welcome_email": 0}
		).insert(ignore_permissions=True)

	employee = frappe.db.get_value("Employee", {"user_id": email}, "name")
	if employee:
		return employee

	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": first_name,
				"date_of_birth": add_years(getdate(), -30),
				"date_of_joining": add_years(getdate(), -1),
				"company": company,
				"status": "Active",
				"user_id": email,
				"cell_number": mobile,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
