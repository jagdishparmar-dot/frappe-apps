"""Storage of Employee Documents, shared by the onboarding and documents APIs."""

import frappe

from hrms_custom.api.response import ApiError
from hrms_custom.hrms_custom.doctype.employee_document.employee_document import DEFAULT_CATEGORY

DOCUMENT_TYPES = tuple(DEFAULT_CATEGORY)
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Extension -> required leading bytes, so a renamed executable is not accepted as a "PDF".
ALLOWED_FILE_SIGNATURES = {
	"pdf": (b"%PDF",),
	"jpg": (b"\xff\xd8\xff",),
	"jpeg": (b"\xff\xd8\xff",),
	"png": (b"\x89PNG\r\n\x1a\n",),
}
MIME_TYPES = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}

DOCUMENT_FIELDS = [
	"name",
	"employee",
	"document_type",
	"category",
	"status",
	"file",
	"file_name",
	"remarks",
	"verified_by",
	"verified_on",
	"creation",
]


def read_request_file() -> tuple[str, bytes]:
	"""The `file` part of the current multipart request."""
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload or not upload.filename:
		raise ApiError("Please choose a file to upload", 400)
	return upload.filename, upload.stream.read()


def save_employee_document(employee: str, document_type: str | None, filename: str, content: bytes) -> dict:
	"""Validate an upload and store it as a private File on the Employee plus a Pending Employee Document."""
	if document_type not in DOCUMENT_TYPES:
		raise ApiError("Select a valid document type", 400)
	if not content:
		raise ApiError("The file is empty", 400)
	if len(content) > MAX_UPLOAD_BYTES:
		raise ApiError("File is too large (maximum 5 MB)", 400)

	extension = file_extension(filename)
	signatures = ALLOWED_FILE_SIGNATURES.get(extension)
	if not signatures:
		raise ApiError("Only PDF, JPG and PNG files are allowed", 400)
	if not content.startswith(signatures):
		raise ApiError("The file content does not match its type", 400)

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{frappe.scrub(document_type)}_{frappe.generate_hash(length=8)}.{extension}",
			"content": content,
			"is_private": 1,
			"attached_to_doctype": "Employee",
			"attached_to_name": employee,
		}
	).insert(ignore_permissions=True)

	document = frappe.get_doc(
		{
			"doctype": "Employee Document",
			"employee": employee,
			"document_type": document_type,
			"category": DEFAULT_CATEGORY[document_type],
			"file": file_doc.file_url,
			"file_name": filename[:140],
		}
	).insert(ignore_permissions=True)
	return document_dict(document)


def list_employee_documents(employee: str) -> list[dict]:
	return [
		document_dict(d)
		for d in frappe.get_all(
			"Employee Document",
			filters={"employee": employee},
			fields=DOCUMENT_FIELDS,
			order_by="creation desc",
		)
	]


def delete_employee_document(name: str) -> None:
	"""Delete the document row and its File (only the File attached to the same employee)."""
	row = frappe.db.get_value("Employee Document", name, ["employee", "file"], as_dict=True)
	frappe.delete_doc("Employee Document", name, ignore_permissions=True)
	for file_name in frappe.get_all(
		"File",
		filters={"file_url": row.file, "attached_to_doctype": "Employee", "attached_to_name": row.employee},
		pluck="name",
	):
		frappe.delete_doc("File", file_name, ignore_permissions=True)


def document_dict(d) -> dict:
	return {
		"name": d.name,
		"document_type": d.document_type,
		"category": d.category,
		"status": d.status,
		"file_name": d.file_name,
		"remarks": d.remarks,
		"verified_by": d.get("verified_by"),
		"verified_on": d.get("verified_on"),
		"uploaded_on": d.get("creation"),
	}


def file_extension(filename: str | None) -> str:
	return filename.rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
