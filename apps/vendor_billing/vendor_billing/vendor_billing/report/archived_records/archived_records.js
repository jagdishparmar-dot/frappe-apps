frappe.query_reports["Archived Records"] = {
	filters: [
		{
			fieldname: "doctype",
			label: __("Document Type"),
			fieldtype: "Select",
			options: "VB Invoice\nVB Vendor\nVB Agreement",
			default: "VB Invoice",
			reqd: 1,
		},
	],
};
