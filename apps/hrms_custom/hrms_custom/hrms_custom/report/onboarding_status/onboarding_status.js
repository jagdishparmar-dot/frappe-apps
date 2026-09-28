frappe.query_reports["Onboarding Status"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{
			fieldname: "onboarding_status",
			label: __("Onboarding Status"),
			fieldtype: "Select",
			options: "\nInvited\nPending Verification\nVerified",
		},
		{
			fieldname: "checklist_status",
			label: __("Checklist Status"),
			fieldtype: "Select",
			options: "\nNot Started\nIn Progress\nCompleted",
		},
	],
};
