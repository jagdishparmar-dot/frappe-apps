"""Employee documents (spec section 7): employees upload and view their own, HR verifies or rejects."""

import frappe
from werkzeug.wrappers import Response

from hrms_custom.api.response import ApiError, api_endpoint, success
from hrms_custom.api.session import get_session_employee
from hrms_custom.hrms_custom.doctype.employee_document.employee_document import REVIEWED_STATUSES
from hrms_custom.permissions import is_hr
from hrms_custom.utils.documents import (
	DOCUMENT_FIELDS,
	DOCUMENT_TYPES,
	MIME_TYPES,
	delete_employee_document,
	document_dict,
	file_extension,
	list_employee_documents,
	read_request_file,
	save_employee_document,
)


@frappe.whitelist(methods=["GET"])
@api_endpoint
def list_documents(employee=None):
	"""Documents of `employee` (HR only) or, by default, of the logged-in employee."""
	target = _resolve_employee(employee)
	return {
		"employee": target,
		"documents": list_employee_documents(target),
		"document_types": list(DOCUMENT_TYPES),
	}


@frappe.whitelist(methods=["POST"])
@api_endpoint
def upload_document(document_type=None, replaces=None):
	"""Employee: multipart upload (`file` part). `replaces` names one of their Rejected documents,
	which is removed once the new copy is stored."""
	employee = get_session_employee(("name",)).name
	replaced = None
	if replaces:
		replaced = frappe.db.get_value("Employee Document", replaces, ["employee", "status"], as_dict=True)
		if not replaced or replaced.employee != employee:
			raise ApiError("Document not found", 404)
		if replaced.status != "Rejected":
			raise ApiError("Only a rejected document can be replaced", 409)

	filename, content = read_request_file()
	document = save_employee_document(employee, document_type, filename, content)
	if replaced:
		delete_employee_document(replaces)
	return success(document, "Document uploaded. HR will review it.")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def delete_document(document=None):
	"""Employee: remove one of their own documents that HR has not reviewed yet."""
	employee = get_session_employee(("name",)).name
	row = _get_document(document)
	if row.employee != employee:
		raise ApiError("Document not found", 404)
	if row.status != "Pending":
		raise ApiError("A reviewed document cannot be removed. Please contact HR.", 409)
	delete_employee_document(document)
	return success({"document": document}, "Document removed")


@frappe.whitelist(methods=["POST"])
@api_endpoint
def verify_document(document=None, status=None, remarks=None):
	"""HR: set a document to Verified or Rejected (remarks required for Rejected); the employee is emailed."""
	if not is_hr():
		raise ApiError("Only HR can verify documents", 403)
	if status not in REVIEWED_STATUSES:
		raise ApiError("Status must be Verified or Rejected", 400)
	_get_document(document)

	doc = frappe.get_doc("Employee Document", document)
	if doc.status == status and (remarks is None or remarks == doc.remarks):
		return success(document_dict(doc), f"Document is already {status.lower()}")
	doc.status = status
	if remarks is not None:
		doc.remarks = remarks.strip() or None
	doc.save()
	return success(document_dict(doc), f"Document {status.lower()}")


@frappe.whitelist(methods=["GET"])
@api_endpoint
def download_document(document=None):
	"""The file itself, for its owner or HR. Private files are never served from a public URL."""
	row = _get_document(document)
	if not is_hr() and row.employee != get_session_employee(("name",)).name:
		raise ApiError("Document not found", 404)

	file_name = frappe.db.get_value(
		"File",
		{"file_url": row.file, "attached_to_doctype": "Employee", "attached_to_name": row.employee},
		"name",
	) or frappe.db.get_value("File", {"file_url": row.file}, "name")
	if not file_name:
		raise ApiError("The file for this document is missing", 404)

	# File.get_content() decodes content as text, which corrupts images and PDFs; read raw bytes.
	with open(frappe.get_doc("File", file_name).get_full_path(), "rb") as f:
		content = f.read()
	extension = file_extension(row.file_name) or file_extension(row.file)
	download_name = (row.file_name or f"{document}.{extension}").replace('"', "")
	return Response(
		content,
		status=200,
		mimetype=MIME_TYPES.get(extension, "application/octet-stream"),
		headers={
			"Content-Disposition": f'inline; filename="{download_name}"',
			"Cache-Control": "private, no-store",
		},
	)


def _resolve_employee(employee: str | None) -> str:
	if employee and is_hr():
		if not frappe.db.exists("Employee", employee):
			raise ApiError("Employee not found", 404)
		return employee
	own = get_session_employee(("name",)).name
	if employee and employee != own:
		raise ApiError("You can only view your own documents", 403)
	return own


def _get_document(name: str | None) -> frappe._dict:
	row = frappe.db.get_value("Employee Document", name, DOCUMENT_FIELDS, as_dict=True) if name else None
	if not row:
		raise ApiError("Document not found", 404)
	return row
