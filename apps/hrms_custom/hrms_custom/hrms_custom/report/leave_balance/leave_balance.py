from hrms_custom.utils.reports import leave_balance_rows


def execute(filters=None):
	columns = [
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": "Leave Type", "fieldname": "leave_type", "fieldtype": "Link", "options": "Leave Type", "width": 150},
		{"label": "Allocated", "fieldname": "allocated", "fieldtype": "Float", "width": 100, "precision": 1},
		{"label": "Taken", "fieldname": "taken", "fieldtype": "Float", "width": 90, "precision": 1},
		{"label": "Pending", "fieldname": "pending", "fieldtype": "Float", "width": 90, "precision": 1},
		{"label": "Available", "fieldname": "available", "fieldtype": "Float", "width": 100, "precision": 1},
		{"label": "LWP", "fieldname": "is_lwp", "fieldtype": "Check", "width": 70},
		{"label": "Year", "fieldname": "year", "fieldtype": "Int", "width": 80},
	]
	return columns, leave_balance_rows(filters)
