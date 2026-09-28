frappe.query_reports["Leave Balance"] = {
	filters: [
		{ fieldname: "year", label: __("Year"), fieldtype: "Int", default: frappe.datetime.get_today().slice(0, 4), reqd: 1 },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
		{ fieldname: "leave_type", label: __("Leave Type"), fieldtype: "Link", options: "Leave Type" },
	],
};
