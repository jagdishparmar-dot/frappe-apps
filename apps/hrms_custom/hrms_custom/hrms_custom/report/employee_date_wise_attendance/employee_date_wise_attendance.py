from hrms_custom.utils.reports import employee_date_attendance_rows


def execute(filters=None):
	columns = [
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
		{"label": "Designation", "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 130},
		{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": "In", "fieldname": "in_time", "fieldtype": "Datetime", "width": 160},
		{"label": "Out", "fieldname": "out_time", "fieldtype": "Datetime", "width": 160},
		{"label": "Regularized", "fieldname": "regularized", "fieldtype": "Data", "width": 120},
		{"label": "Actual In", "fieldname": "actual_in_time", "fieldtype": "Time", "width": 110},
		{"label": "Actual Out", "fieldname": "actual_out_time", "fieldtype": "Time", "width": 110},
		{"label": "Regularized In", "fieldname": "regularized_in_time", "fieldtype": "Time", "width": 130},
		{"label": "Regularized Out", "fieldname": "regularized_out_time", "fieldtype": "Time", "width": 140},
		{"label": "Hours", "fieldname": "worked_hours", "fieldtype": "Data", "width": 90},
		{"label": "Shift", "fieldname": "shift_type", "fieldtype": "Data", "width": 120},
	]
	return columns, employee_date_attendance_rows(filters)
