# Copyright (c) 2026, Vendor Directory and contributors
# For license information, please see license.txt

import os

import frappe


def debug_form():
	meta = frappe.get_meta("Vendor")
	tabs = [f.label for f in meta.fields if f.fieldtype == "Tab Break"]
	sections = [f.label for f in meta.fields if f.fieldtype == "Section Break"]
	js_path = frappe.get_app_path(
		"vendor_directory", "vendor_directory", "doctype", "vendor", "vendor.js"
	)
	return {
		"field_count": len(meta.fields),
		"tabs": tabs,
		"sections": sections,
		"list_view": [f.fieldname for f in meta.fields if f.in_list_view],
		"js_exists": os.path.exists(js_path),
		"js_size": os.path.getsize(js_path) if os.path.exists(js_path) else 0,
		"module_def": frappe.db.exists("Module Def", "Vendor Directory"),
		"workspaces": frappe.get_all(
			"Workspace", filters={"module": "Vendor Directory"}, pluck="name"
		),
		"has_permission": frappe.has_permission("Vendor", "read"),
	}
