from hrms_custom.utils.reports import onboarding_status_rows


def execute(filters=None):
	columns = [
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": "Onboarding", "fieldname": "onboarding_status", "fieldtype": "Data", "width": 150},
		{"label": "Employment Status", "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": "Date of Joining", "fieldname": "date_of_joining", "fieldtype": "Date", "width": 120},
		{"label": "Checklist", "fieldname": "checklist", "fieldtype": "Link", "options": "Onboarding Checklist", "width": 150},
		{"label": "Checklist Status", "fieldname": "checklist_status", "fieldtype": "Data", "width": 130},
		{"label": "Pending Docs", "fieldname": "documents_pending", "fieldtype": "Int", "width": 110},
		{"label": "Verified Docs", "fieldname": "documents_verified", "fieldtype": "Int", "width": 110},
		{"label": "Rejected Docs", "fieldname": "documents_rejected", "fieldtype": "Int", "width": 110},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
	]
	return columns, onboarding_status_rows(filters)
