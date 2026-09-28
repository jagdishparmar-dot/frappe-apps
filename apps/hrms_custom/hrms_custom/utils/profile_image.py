"""Private Employee profile photos, stored as a File on the Employee.image field."""

import frappe
from werkzeug.wrappers import Response

from hrms_custom.api.response import ApiError
from hrms_custom.utils.documents import ALLOWED_FILE_SIGNATURES, MIME_TYPES, file_extension, read_request_file

MAX_PROFILE_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = {ext: ALLOWED_FILE_SIGNATURES[ext] for ext in ("jpg", "jpeg", "png")}


def save_profile_image(employee: str, filename: str, content: bytes) -> str:
	"""Replace the Employee photo. Returns the new File URL."""
	if not content:
		raise ApiError("The file is empty", 400)
	if len(content) > MAX_PROFILE_IMAGE_BYTES:
		raise ApiError("File is too large (maximum 5 MB)", 400)

	extension = file_extension(filename)
	signatures = IMAGE_SIGNATURES.get(extension)
	if not signatures:
		raise ApiError("Only JPG and PNG photos are allowed", 400)
	if not content.startswith(signatures):
		raise ApiError("The file content does not match its type", 400)

	previous = frappe.db.get_value("Employee", employee, "image")
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"profile_{frappe.generate_hash(length=8)}.{extension}",
			"content": content,
			"is_private": 1,
			"attached_to_doctype": "Employee",
			"attached_to_name": employee,
		}
	).insert(ignore_permissions=True)

	doc = frappe.get_doc("Employee", employee)
	doc.flags.ignore_permissions = True
	doc.image = file_doc.file_url
	doc.save()

	if previous and previous != file_doc.file_url:
		_delete_attached_file(employee, previous)
	return file_doc.file_url


def clear_profile_image(employee: str) -> None:
	previous = frappe.db.get_value("Employee", employee, "image")
	doc = frappe.get_doc("Employee", employee)
	doc.flags.ignore_permissions = True
	doc.image = None
	doc.save()
	if previous:
		_delete_attached_file(employee, previous)


def profile_image_response(employee: str, file_url: str | None) -> Response:
	if not file_url:
		raise ApiError("No profile photo uploaded", 404)
	file_name = frappe.db.get_value(
		"File",
		{"file_url": file_url, "attached_to_doctype": "Employee", "attached_to_name": employee},
		"name",
	) or frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		raise ApiError("The profile photo is missing", 404)

	file_doc = frappe.get_doc("File", file_name)
	with open(file_doc.get_full_path(), "rb") as f:
		content = f.read()
	extension = file_extension(file_doc.file_name) or file_extension(file_url)
	return Response(
		content,
		status=200,
		mimetype=MIME_TYPES.get(extension, "image/jpeg"),
		headers={
			"Content-Disposition": 'inline; filename="profile-photo"',
			"Cache-Control": "private, no-store",
		},
	)


def read_uploaded_image() -> tuple[str, bytes]:
	return read_request_file()


def _delete_attached_file(employee: str, file_url: str) -> None:
	for name in frappe.get_all(
		"File",
		filters={"file_url": file_url, "attached_to_doctype": "Employee", "attached_to_name": employee},
		pluck="name",
	):
		frappe.delete_doc("File", name, ignore_permissions=True)
