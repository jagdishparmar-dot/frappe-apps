from hrms_custom.utils.reports import late_early_rows


def execute(filters=None):
	columns = [
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": "Shift", "fieldname": "shift_type", "fieldtype": "Link", "options": "Shift Type", "width": 140},
		{"label": "In Time", "fieldname": "in_time", "fieldtype": "Datetime", "width": 170},
		{"label": "Out Time", "fieldname": "out_time", "fieldtype": "Datetime", "width": 170},
		{"label": "Regularized", "fieldname": "regularized", "fieldtype": "Data", "width": 120},
		{"label": "Actual In", "fieldname": "actual_in_time", "fieldtype": "Time", "width": 110},
		{"label": "Actual Out", "fieldname": "actual_out_time", "fieldtype": "Time", "width": 110},
		{"label": "Regularized In", "fieldname": "regularized_in_time", "fieldtype": "Time", "width": 130},
		{"label": "Regularized Out", "fieldname": "regularized_out_time", "fieldtype": "Time", "width": 140},
		{"label": "Late (min)", "fieldname": "late_minutes", "fieldtype": "Int", "width": 100},
		{"label": "Early (min)", "fieldname": "early_minutes", "fieldtype": "Int", "width": 100},
	]
	return columns, late_early_rows(filters)
