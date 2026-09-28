frappe.query_reports["Employee Master"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nActive\nInactive\nSuspended\nLeft",
		},
		{
			fieldname: "onboarding_status",
			label: __("Onboarding Status"),
			fieldtype: "Select",
			options: "\nInvited\nPending Verification\nVerified",
		},
		{
			fieldname: "employee_type",
			label: __("Employee Type"),
			fieldtype: "Select",
			options: "\nPermanent\nContract\nOther",
		},
		{ fieldname: "vendor", label: __("Vendor"), fieldtype: "Link", options: "Vendor" },
	],
};
