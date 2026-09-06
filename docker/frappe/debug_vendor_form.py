import json
import frappe

frappe.init(site="vendors.localhost", sites_path="/home/frappe/frappe-bench/sites")
frappe.connect()
frappe.set_user("Administrator")

meta = frappe.get_meta("Vendor")
print("FIELD_COUNT", len(meta.fields))
print("TITLE", meta.title_field)
print("AUTONAME", meta.autoname)
tabs = [f.label for f in meta.fields if f.fieldtype == "Tab Break"]
print("TABS", tabs)

# Simulate desk form load
from frappe.desk.form.load import getdoctype
docs = getdoctype("Vendor")
# docs is a message with docs list
payload = docs
if hasattr(docs, "as_dict"):
    payload = docs
print("GETDOCTYPE_TYPE", type(docs))
# In newer frappe getdoctype returns None and pushes to local.response
from frappe import local
msg = local.response.get("docs") or local.response.get("message")
print("RESPONSE_KEYS", list(local.response.keys()))
if "docs" in local.response:
    for d in local.response["docs"]:
        if d.get("name") == "Vendor" or d.get("doctype") == "DocType":
            print("DOC", d.get("doctype"), d.get("name"), "fields", len(d.get("fields") or []))
            tabs2 = [f.get("label") for f in (d.get("fields") or []) if f.get("fieldtype") == "Tab Break"]
            print("DOC_TABS", tabs2)

# Check if JS loads
from frappe.modules import get_doctype_module, scrub
import os
js_path = frappe.get_app_path("vendor_directory", "vendor_directory", "doctype", "vendor", "vendor.js")
print("JS_PATH", js_path, "EXISTS", os.path.exists(js_path))
if os.path.exists(js_path):
    print("JS_SIZE", os.path.getsize(js_path))

# List view fields
print("LIST_VIEW", [f.fieldname for f in meta.fields if f.in_list_view])

# Module
print("MODULE_EXISTS", frappe.db.exists("Module Def", "Vendor Directory"))
print("WORKSPACES", frappe.get_all("Workspace", filters={"module": "Vendor Directory"}, pluck="name"))

frappe.destroy()
