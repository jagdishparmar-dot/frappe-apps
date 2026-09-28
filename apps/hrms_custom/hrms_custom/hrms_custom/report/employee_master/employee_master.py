from hrms_custom.utils.reports import employee_master_rows


def execute(filters=None):
	columns = [
		{"label": "Employee", "fieldname": "name", "fieldtype": "Link", "options": "Employee", "width": 140},
		{"label": "Full Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Onboarding", "fieldname": "onboarding_status", "fieldtype": "Data", "width": 140},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
		{"label": "Designation", "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 140},
		{"label": "Employee Type", "fieldname": "employee_type", "fieldtype": "Data", "width": 110},
		{"label": "Vendor", "fieldname": "vendor", "fieldtype": "Link", "options": "Vendor", "width": 160},
		{"label": "Other Type", "fieldname": "other_employee_type", "fieldtype": "Data", "width": 120},
		{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
		{"label": "Date of Joining", "fieldname": "date_of_joining", "fieldtype": "Date", "width": 120},
		{"label": "Mobile", "fieldname": "cell_number", "fieldtype": "Data", "width": 120},
		{"label": "Personal Email", "fieldname": "personal_email", "fieldtype": "Data", "width": 180},
		{"label": "User", "fieldname": "user_id", "fieldtype": "Link", "options": "User", "width": 180},
	]
	return columns, employee_master_rows(filters)
