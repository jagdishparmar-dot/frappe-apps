import base64

import frappe
from frappe import _
from frappe.utils.file_manager import save_file

from hr_portal.api.serialize import staff_or_own
from hr_portal.permissions import get_employee_name, is_staff
from hr_portal.utils import require_login


ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_PROFILE_PICTURE_BYTES = 5 * 1024 * 1024
CATEGORIES = {"profile_picture", "identity", "compliance", "employment"}


def _file_url(name: str) -> str:
	return frappe.utils.get_url(f"/api/method/hr_portal.api.documents.download_file?name={name}")


def document_payload(doc) -> dict:
	return {
		"id": doc.name,
		"employeeId": doc.employee,
		"category": doc.category,
		"title": doc.title,
		"fileId": doc.file,
		"fileName": doc.file_name,
		"mimeType": doc.mime_type,
		"fileSize": int(doc.file_size or 0),
		"status": (doc.status or "Active").lower(),
		"previewUrl": _file_url(doc.name),
	}


def list_documents(employee: str, include_archived: bool = False) -> list[dict]:
	filters: dict = {"employee": employee}
	if not include_archived:
		filters["status"] = "Active"
	rows = frappe.get_all(
		"HR Employee Document",
		filters=filters,
		fields=["name", "employee", "category", "title", "file", "file_name", "mime_type", "file_size", "status"],
		order_by="modified desc",
		limit=100,
	)
	return [document_payload(frappe._dict(row)) for row in rows]


def _decode_upload(file_name: str, mime_type: str, data_base64: str, category: str) -> tuple[bytes, str, str]:
	mime_type = (mime_type or "").strip().lower()
	if mime_type == "image/jpg":
		mime_type = "image/jpeg"
	if mime_type not in ALLOWED_MIME:
		frappe.throw(_("File type is not allowed"))
	try:
		content = base64.b64decode(data_base64)
	except Exception:
		frappe.throw(_("Invalid file data"))
	limit = MAX_PROFILE_PICTURE_BYTES if category == "profile_picture" else MAX_DOCUMENT_BYTES
	if len(content) > limit:
		frappe.throw(_("File is too large"))
	name = (file_name or "upload").strip() or "upload"
	return content, name, mime_type


@frappe.whitelist()
def list_employee_documents(employee: str) -> dict:
	require_login()
	staff_or_own(employee)
	return {"documents": list_documents(employee)}


@frappe.whitelist()
def upload_document(
	employee: str | None = None,
	category: str = "employment",
	title: str = "",
	file_name: str = "",
	mime_type: str = "",
	data_base64: str = "",
) -> dict:
	require_login()
	category = (category or "").strip()
	if category not in CATEGORIES:
		frappe.throw(_("Invalid document category"))
	own = get_employee_name()
	target = (employee or own or "").strip()
	if not target:
		frappe.throw(_("No employee record found"))
	if target != own and not is_staff() and frappe.session.user != "Administrator":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if own == target:
		pass
	elif not is_staff() and frappe.session.user != "Administrator":
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	content, stored_name, mime_type = _decode_upload(file_name, mime_type, data_base64, category)
	doc = frappe.get_doc(
		{
			"doctype": "HR Employee Document",
			"employee": target,
			"category": category,
			"title": (title or stored_name).strip(),
			"file_name": stored_name,
			"mime_type": mime_type,
			"file_size": len(content),
			"status": "Active",
			"file": "",
		}
	)
	doc.flags.ignore_mandatory = True
	doc.insert()
	file_doc = save_file(stored_name, content, "HR Employee Document", doc.name, is_private=1, df="file")
	doc.file = file_doc.file_url
	doc.file_size = len(content)
	doc.save()

	if category == "profile_picture":
		frappe.db.set_value("HR Employee", target, "image", file_doc.file_url)

	return {"ok": True, "document": document_payload(doc)}


@frappe.whitelist()
def delete_document(name: str) -> dict:
	require_login()
	doc = frappe.get_doc("HR Employee Document", name)
	staff_or_own(doc.employee)
	own = get_employee_name()
	if doc.employee != own and not is_staff() and frappe.session.user != "Administrator":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	doc.status = "Archived"
	doc.save()
	return {"ok": True}


@frappe.whitelist()
def download_file(name: str):
	require_login()
	doc = frappe.get_doc("HR Employee Document", name)
	if not doc.has_permission("read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not doc.file:
		frappe.throw(_("File not found"))
	file_doc = frappe.get_doc("File", {"file_url": doc.file})
	frappe.local.response.filename = doc.file_name or file_doc.file_name
	frappe.local.response.filecontent = file_doc.get_content()
	frappe.local.response.type = "download"
