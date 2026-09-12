frappe.query_reports["Invoice Remarks"] = {
	filters: [
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nHold\nRejected\nPaid\nPending",
		},
	],
};
