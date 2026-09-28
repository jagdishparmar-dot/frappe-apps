"""Attendance regularization request and HR review (spec section 8)."""

import frappe

from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import get_session_employee
from hrms_custom.permissions import is_hr
from hrms_custom.utils.regularization import (
	REVIEWED_STATUSES,
	load_regularization,
	regularization_dict,
	validate_request,
)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def my_regularizations(status=None):
	"""The session employee's regularization requests, newest first."""
	employee = get_session_employee(("name",))
	filters = {"employee": employee.name}
	if status:
		filters["status"] = status
	names = frappe.get_all(
		"Attendance Regularization",
		filters=filters,
		pluck="name",
		order_by="creation desc",
		limit=100,
		ignore_permissions=True,
	)
	return {"requests": [regularization_dict(load_regularization(name)) for name in names]}


@frappe.whitelist(methods=["POST"])
@api_endpoint
def request_regularization(date=None, requested_check_in=None, requested_check_out=None, reason=None):
	"""Create an Open regularization for the session employee."""
	employee = get_session_employee(("name",))
	preview = validate_request(employee.name, date, requested_check_in, requested_check_out, reason)
	doc = frappe.get_doc(
		{
			"doctype": "Attendance Regularization",
			"employee": employee.name,
			"date": preview["date"],
			"requested_check_in": preview["requested_check_in"],
			"requested_check_out": preview["requested_check_out"],
			"reason": preview["reason"],
			"status": "Open",
		}
	).insert(ignore_permissions=True)
	return success(regularization_dict(doc), "Regularization submitted")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def cancel_regularization(request=None):
	"""Employee: cancel an Open request of their own."""
	employee = get_session_employee(("name",))
	if not request:
		raise ApiError("request is required", 400)
	doc = load_regularization(request)
	if doc.employee != employee.name and not is_hr():
		raise ApiError("You can only cancel your own regularization", 403)
	if doc.status != "Open":
		raise ApiError("Only an open regularization can be cancelled", 409)
	doc.status = "Cancelled"
	doc.save(ignore_permissions=True)
	return success(regularization_dict(doc), "Regularization cancelled")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def review_regularization(request=None, status=None, remarks=None):
	"""HR: approve or reject an Open request. Approval writes Employee Checkin rows."""
	if not is_hr():
		raise ApiError("Only HR can review regularization", 403)
	if not request or status not in REVIEWED_STATUSES:
		raise ApiError("request and status (Approved or Rejected) are required", 400)
	doc = load_regularization(request)
	if doc.status != "Open":
		raise ApiError("Only an open regularization can be reviewed", 409)
	doc.status = status
	doc.remarks = remarks
	doc.save()
	return success(regularization_dict(load_regularization(doc.name)), f"Regularization {status.lower()}")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def approve_regularization(request=None, remarks=None):
	"""Spec alias for reviewing a request as Approved."""
	return review_regularization(request=request, status="Approved", remarks=remarks)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_regularizations(employee=None, status=None):
	"""HR: list requests. Employees only see their own."""
	filters = {}
	if not is_hr():
		session = get_session_employee(("name",))
		if employee and employee != session.name:
			raise ApiError("You can only list your own regularizations", 403)
		filters["employee"] = session.name
	elif employee:
		filters["employee"] = employee
	if status:
		filters["status"] = status
	names = frappe.get_all(
		"Attendance Regularization",
		filters=filters,
		pluck="name",
		order_by="creation desc",
		limit=100,
		ignore_permissions=True,
	)
	return {"requests": [regularization_dict(load_regularization(name)) for name in names]}
