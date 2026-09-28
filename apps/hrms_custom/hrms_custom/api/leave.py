"""Leave balance, apply, and HR review (spec section 10)."""

import frappe
from frappe.utils import cint

from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import get_session_employee
from hrms_custom.permissions import is_hr
from hrms_custom.utils.leave import (
	REVIEWED_STATUSES,
	application_dict,
	build_balance,
	load_application,
	preview_application,
)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def my_leave_balance(year=None):
	"""Balances per active leave type for the logged-in employee (year defaults to current)."""
	employee = get_session_employee(("name", "company"))
	return build_balance(employee.name, employee.company, year)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def my_leave_applications(status=None):
	"""The session employee's leave applications, newest first."""
	employee = get_session_employee(("name",))
	filters = {"employee": employee.name}
	if status:
		filters["status"] = status
	names = frappe.get_all(
		"Leave Application",
		filters=filters,
		pluck="name",
		order_by="creation desc",
		limit=100,
		ignore_permissions=True,
	)
	return {"applications": [application_dict(load_application(name)) for name in names]}


@frappe.whitelist(methods=["GET", "POST"])
@api_endpoint
def preview_leave(leave_type=None, from_date=None, to_date=None, half_day=0, half_day_date=None):
	"""Validate a draft application and return the counted days and remaining balance."""
	employee = get_session_employee(("name", "company"))
	if not leave_type or not from_date or not to_date:
		raise ApiError("Leave type, from date and to date are required", 400)
	return preview_application(
		employee.name,
		employee.company,
		leave_type,
		from_date,
		to_date,
		half_day=half_day,
		half_day_date=half_day_date,
	)


@frappe.whitelist(methods=["POST"])
@api_endpoint
def apply_leave(leave_type=None, from_date=None, to_date=None, half_day=0, half_day_date=None, reason=None):
	"""Create an Open leave application for the session employee."""
	employee = get_session_employee(("name", "company"))
	if not leave_type or not from_date or not to_date:
		raise ApiError("Leave type, from date and to date are required", 400)
	preview_application(
		employee.name,
		employee.company,
		leave_type,
		from_date,
		to_date,
		half_day=half_day,
		half_day_date=half_day_date,
	)
	doc = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": employee.name,
			"leave_type": leave_type,
			"from_date": from_date,
			"to_date": to_date,
			"half_day": cint(half_day),
			"half_day_date": half_day_date,
			"reason": reason,
			"status": "Open",
		}
	).insert(ignore_permissions=True)
	return success(application_dict(doc), "Leave application submitted")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def cancel_leave(application=None):
	"""Employee: cancel an Open application of their own."""
	employee = get_session_employee(("name",))
	if not application:
		raise ApiError("application is required", 400)
	doc = load_application(application)
	if doc.employee != employee.name and not is_hr():
		raise ApiError("You can only cancel your own leave", 403)
	if doc.status != "Open":
		raise ApiError("Only an open leave application can be cancelled", 409)
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)
	return success(application_dict(doc), "Leave application cancelled")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_leave(application=None, status=None, remarks=None):
	"""HR: approve or reject an Open application."""
	if not is_hr():
		raise ApiError("Only HR can review leave", 403)
	if not application or status not in REVIEWED_STATUSES:
		raise ApiError("application and status (Approved or Rejected) are required", 400)
	doc = load_application(application)
	if doc.status != "Open":
		raise ApiError("Only an open leave application can be reviewed", 409)
	doc.status = status
	doc.remarks = remarks
	doc.save()
	return success(application_dict(doc), f"Leave {status.lower()}")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_leave_applications(employee=None, status=None):
	"""HR: list applications. Employees only see their own."""
	filters = {}
	if not is_hr():
		session = get_session_employee(("name",))
		if employee and employee != session.name:
			raise ApiError("You can only list your own leave", 403)
		filters["employee"] = session.name
	elif employee:
		filters["employee"] = employee
	if status:
		filters["status"] = status
	names = frappe.get_all(
		"Leave Application",
		filters=filters,
		pluck="name",
		order_by="creation desc",
		limit=100,
		ignore_permissions=True,
	)
	return {"applications": [application_dict(load_application(name)) for name in names]}
