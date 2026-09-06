# Copyright (c) 2026, Vendor Directory and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

PORTAL_EDITABLE_FIELDS = {
	"vendor_name",
	"contact_person",
	"email",
	"phone",
	"website",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"pincode",
	"country",
	"gstin",
	"pan",
	"gst_registration_type",
	"place_of_supply",
	"bank_name",
	"account_holder_name",
	"account_number",
	"ifsc_code",
	"branch",
	"upi_id",
	"notes",
}


class Vendor(Document):
	def validate(self):
		self._normalize_codes()
		self._validate_gstin()
		self._validate_pan()
		self._validate_ifsc()
		self._validate_portal_user()
		self._stamp_kyc_documents()

	def on_update(self):
		self._sync_kyc_review_fields()

	def _normalize_codes(self):
		if self.gstin:
			self.gstin = self.gstin.strip().upper()
		if self.pan:
			self.pan = self.pan.strip().upper()
		if self.ifsc_code:
			self.ifsc_code = self.ifsc_code.strip().upper()
		if self.vendor_code:
			self.vendor_code = self.vendor_code.strip().upper()
		if self.portal_login_id:
			self.portal_login_id = self.portal_login_id.strip().lower()

	def _validate_gstin(self):
		if not self.gstin:
			return
		if self.gst_registration_type == "Unregistered":
			return
		if not GSTIN_RE.match(self.gstin):
			frappe.throw(_("Invalid GSTIN format. Expected 15-character Indian GSTIN."))

	def _validate_pan(self):
		if not self.pan:
			return
		if not PAN_RE.match(self.pan):
			frappe.throw(_("Invalid PAN format. Expected format: AAAAA9999A."))

	def _validate_ifsc(self):
		if not self.ifsc_code:
			return
		if not IFSC_RE.match(self.ifsc_code):
			frappe.throw(_("Invalid IFSC code format."))

	def _validate_portal_user(self):
		if self.portal_user and self.portal_enabled is None:
			self.portal_enabled = 1
		if self.portal_login_id:
			existing = frappe.db.get_value(
				"Vendor",
				{"portal_login_id": self.portal_login_id, "name": ("!=", self.name)},
				"name",
			)
			if existing:
				frappe.throw(_("Portal Login ID already linked to vendor {0}").format(existing))

	def _stamp_kyc_documents(self):
		for row in self.get("kyc_documents") or []:
			if not row.uploaded_on:
				row.uploaded_on = now_datetime()
			if not row.uploaded_by:
				row.uploaded_by = frappe.session.user

	def _sync_kyc_review_fields(self):
		# populated by API / desk when admin changes status
		pass


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	if "System Manager" in roles or "Vendor Manager" in roles:
		return ""
	if "Vendor Portal User" in roles:
		return f"`tabVendor`.portal_user = {frappe.db.escape(user)} AND IFNULL(`tabVendor`.portal_enabled, 0) = 1"
	return "1=0"


def has_permission(doc, ptype="read", user=None):
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	if "System Manager" in roles or "Vendor Manager" in roles:
		return True
	if "Vendor Portal User" in roles:
		if not getattr(doc, "portal_enabled", 0):
			return False
		return doc.portal_user == user
	return False
