from calendar import monthrange

from hrms_custom.utils.reports import monthly_attendance_grid_rows, report_month


def execute(filters=None):
	first = report_month(filters)
	_, days_in_month = monthrange(first.year, first.month)
	columns = [
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 170},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 140},
		{"label": "Department", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
		{"label": "Designation", "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 130},
		{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
	]
	for day in range(1, days_in_month + 1):
		columns.append({"label": str(day), "fieldname": f"day_{day}", "fieldtype": "Data", "width": 90})
	columns.extend(
		[
			{"label": "Present", "fieldname": "present", "fieldtype": "Int", "width": 90},
			{"label": "Absent", "fieldname": "absent", "fieldtype": "Int", "width": 90},
			{"label": "Leave", "fieldname": "leave", "fieldtype": "Int", "width": 90},
			{"label": "Half Day", "fieldname": "half_day", "fieldtype": "Int", "width": 90},
		]
	)
	return columns, monthly_attendance_grid_rows(filters)
