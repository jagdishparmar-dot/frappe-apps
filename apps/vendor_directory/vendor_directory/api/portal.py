# Copyright (c) 2026, Vendor Directory and contributors
# For license information, please see license.txt

"""Portal and admin APIs for Vendor Directory."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime, validate_email_address
from frappe.utils.password import update_password

from vendor_directory.vendor_directory.doctype.vendor.vendor import PORTAL_EDITABLE_FIELDS


def _is_admin(user: str | None = None) -> bool:
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	return "System Manager" in roles or "Vendor Manager" in roles


def _get_my_vendor_name(user: str | None = None) -> str:
	user = user or frappe.session.user
	if user in ("Guest", "Administrator") and not _is_admin(user):
		# Administrator may not be a portal vendor
		pass
	name = frappe.db.get_value(
		"Vendor",
		{"portal_user": user, "portal_enabled": 1},
		"name",
	)
	if not name:
		frappe.throw(_("No vendor portal profile is linked to your login."), frappe.PermissionError)
	return name


def _vendor_as_dict(doc) -> dict:
	data = doc.as_dict()
	# hide internal noise for portal
	data.pop("notes", None) if False else None
	return data


@frappe.whitelist()
def get_my_vendor():
	"""Return the Vendor record linked to the logged-in portal user."""
	name = _get_my_vendor_name()
	doc = frappe.get_doc("Vendor", name)
	doc.check_permission("read")
	return _vendor_as_dict(doc)


@frappe.whitelist()
def update_my_vendor(data: str | dict | None = None):
	"""Portal user updates allowed profile fields."""
	if isinstance(data, str):
		data = frappe.parse_json(data)
	data = data or {}

	name = _get_my_vendor_name()
	doc = frappe.get_doc("Vendor", name)
	doc.check_permission("write")

	if doc.kyc_status == "Verified":
		# Still allow contact/address updates after verify, but flag for re-review on sensitive fields
		sensitive = {"gstin", "pan", "account_number", "ifsc_code", "bank_name"}
		if any(k in data and data.get(k) != doc.get(k) for k in sensitive):
			doc.kyc_status = "Pending Review"

	for key, value in data.items():
		if key in PORTAL_EDITABLE_FIELDS:
			doc.set(key, value)

	if doc.kyc_status == "Draft":
		# keep draft until they submit
		pass

	doc.save(ignore_permissions=False)
	return _vendor_as_dict(doc)


@frappe.whitelist()
def submit_for_kyc_review():
	"""Vendor submits profile + documents for admin KYC review."""
	name = _get_my_vendor_name()
	doc = frappe.get_doc("Vendor", name)
	doc.check_permission("write")

	if not doc.get("kyc_documents"):
		frappe.throw(_("Upload at least one KYC document before submitting for review."))

	if doc.kyc_status in ("Pending Review", "Under Review", "Verified"):
		frappe.throw(_("KYC is already {0}.").format(doc.kyc_status))

	doc.kyc_status = "Pending Review"
	doc.save()
	return _vendor_as_dict(doc)


@frappe.whitelist()
def upload_kyc_document(document_type: str, file_url: str, vendor_remarks: str | None = None):
	"""Attach an already-uploaded file URL as a KYC document row."""
	if not document_type or not file_url:
		frappe.throw(_("document_type and file_url are required"))

	name = _get_my_vendor_name()
	doc = frappe.get_doc("Vendor", name)
	doc.check_permission("write")

	doc.append(
		"kyc_documents",
		{
			"document_type": document_type,
			"attachment": file_url,
			"status": "Pending",
			"vendor_remarks": vendor_remarks,
			"uploaded_on": now_datetime(),
			"uploaded_by": frappe.session.user,
		},
	)

	if doc.kyc_status in ("Draft", "Rejected", "Verified"):
		# new docs after verify/reject move back toward review
		if doc.kyc_status == "Verified":
			doc.kyc_status = "Pending Review"
		elif doc.kyc_status == "Rejected":
			doc.kyc_status = "Draft"

	doc.save()
	return _vendor_as_dict(doc)


@frappe.whitelist()
def create_portal_user(vendor: str, login_id: str | None = None, password: str | None = None):
	"""Admin: create / link a User for Vendor Portal access."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Vendor", vendor)
	login_id = (login_id or doc.portal_login_id or doc.email or "").strip().lower()
	if not login_id:
		frappe.throw(_("Provide a login ID (email) for the portal user."))
	validate_email_address(login_id, throw=True)

	if not password:
		password = frappe.generate_hash(length=10)

	created = False
	if frappe.db.exists("User", login_id):
		user = frappe.get_doc("User", login_id)
		if password:
			update_password(user.name, password)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": login_id,
				"first_name": doc.contact_person or doc.vendor_name or login_id.split("@")[0],
				"send_welcome_email": 1 if doc.send_welcome_email else 0,
				"user_type": "Website User",
			}
		)
		user.insert(ignore_permissions=True)
		update_password(user.name, password)
		created = True

	# ensure portal role
	if "Vendor Portal User" not in [r.role for r in user.roles]:
		user.add_roles("Vendor Portal User")

	# disable desk if website user - already Website User
	doc.portal_user = user.name
	doc.portal_login_id = login_id
	doc.portal_enabled = 1
	doc.save(ignore_permissions=True)

	return {
		"vendor": doc.name,
		"portal_user": user.name,
		"portal_login_id": login_id,
		"temporary_password": password if created or password else None,
		"message": _("Portal user linked. Share the login ID and password with the vendor."),
	}


@frappe.whitelist()
def set_kyc_status(vendor: str, kyc_status: str, kyc_remarks: str | None = None, document_updates: str | dict | None = None):
	"""Admin: set KYC status and optional per-document decisions."""
	if not _is_admin():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	allowed = {"Draft", "Pending Review", "Under Review", "Verified", "Rejected"}
	if kyc_status not in allowed:
		frappe.throw(_("Invalid KYC status"))

	doc = frappe.get_doc("Vendor", vendor)
	doc.kyc_status = kyc_status
	if kyc_remarks is not None:
		doc.kyc_remarks = kyc_remarks
	doc.kyc_reviewed_by = frappe.session.user
	doc.kyc_reviewed_on = now_datetime()

	if document_updates:
		if isinstance(document_updates, str):
			document_updates = frappe.parse_json(document_updates)
		# expect list of {idx or name, status, admin_remarks}
		for upd in document_updates or []:
			row = None
			if upd.get("name"):
				row = next((r for r in doc.kyc_documents if r.name == upd["name"]), None)
			elif upd.get("idx") is not None:
				row = next((r for r in doc.kyc_documents if r.idx == int(upd["idx"])), None)
			if not row:
				continue
			if upd.get("status"):
				row.status = upd["status"]
			if "admin_remarks" in upd:
				row.admin_remarks = upd.get("admin_remarks")

	doc.save(ignore_permissions=True)
	return _vendor_as_dict(doc)
