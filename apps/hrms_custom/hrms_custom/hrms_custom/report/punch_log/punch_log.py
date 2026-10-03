from hrms_custom.utils.reports import punch_log_rows


def execute(filters=None):
	columns = [
		{"label": "Time", "fieldname": "time", "fieldtype": "Datetime", "width": 170},
		{"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": "Log Type", "fieldname": "log_type", "fieldtype": "Data", "width": 80},
		{"label": "Regularized", "fieldname": "regularized", "fieldtype": "Data", "width": 120},
		{"label": "Latitude", "fieldname": "latitude", "fieldtype": "Float", "width": 110, "precision": 7},
		{"label": "Longitude", "fieldname": "longitude", "fieldtype": "Float", "width": 110, "precision": 7},
		{"label": "Within Geofence", "fieldname": "is_within_geofence", "fieldtype": "Check", "width": 130},
		{"label": "Geofence Location", "fieldname": "geofence_location", "fieldtype": "Link", "options": "Geofence Location", "width": 160},
		{"label": "Distance (m)", "fieldname": "distance_from_geofence", "fieldtype": "Float", "width": 110, "precision": 1},
		{"label": "Auto Closed", "fieldname": "is_auto_closed", "fieldtype": "Check", "width": 110},
		{"label": "Device", "fieldname": "device_id", "fieldtype": "Data", "width": 140},
	]
	return columns, punch_log_rows(filters)
