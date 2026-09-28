from hrms_custom.utils.reports import attendance_summary_rows


def execute(filters=None):
	columns = [
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
		{"label": "Present", "fieldname": "present", "fieldtype": "Int", "width": 90},
		{"label": "Half Day", "fieldname": "half_day", "fieldtype": "Int", "width": 90},
		{"label": "Absent", "fieldname": "absent", "fieldtype": "Int", "width": 90},
		{"label": "Late", "fieldname": "late", "fieldtype": "Int", "width": 90},
		{"label": "On Leave", "fieldname": "on_leave", "fieldtype": "Int", "width": 90},
	]
	return columns, attendance_summary_rows(filters)
