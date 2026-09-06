import frappe

frappe.init(site="vendors.localhost")
frappe.connect()
meta = frappe.get_meta("Vendor")
for f in meta.fields:
    if f.fieldtype in ("Tab Break", "Section Break", "Column Break", "Table") or f.fieldname in (
        "vendor_name",
        "kyc_documents",
        "kyc_status",
    ):
        print(f"{f.idx:02d}", f.fieldtype, f.fieldname, f.label or "")
frappe.destroy()
