app_name = "hr_portal"
app_title = "HR Portal"
app_publisher = "Intoship"
app_description = "Single-company HR + attendance portal"
app_email = "dev@intoship.cloud"
app_license = "mit"
app_icon_url = "/assets/hr_portal/images/logo.svg"
app_icon_title = "HR"
app_icon_route = "/hr"

required_apps = []

add_to_apps_screen = [
	{
		"name": "hr_portal",
		"logo": "/assets/hr_portal/images/logo.svg",
		"title": "HR",
		"route": "/hr",
		"has_permission": "hr_portal.api.session.check_app_permission",
	}
]

website_route_rules = [
	{"from_route": "/hr/<path:app_path>", "to_route": "hr"},
]

role_home_page = {
	"HR Admin": "hr",
	"HR Manager": "hr",
	"HR Payroll Admin": "hr",
	"HR Reporting Manager": "hr",
	"HR Employee": "hr",
}

after_install = "hr_portal.setup.install.after_install"
after_migrate = "hr_portal.setup.install.after_migrate"

permission_query_conditions = {
	"HR Employee": "hr_portal.permissions.employee_query",
	"HR Employee Document": "hr_portal.permissions.document_query",
	"HR Attendance": "hr_portal.permissions.attendance_query",
	"HR Regularization": "hr_portal.permissions.regularization_query",
	"HR Leave Request": "hr_portal.permissions.leave_request_query",
	"HR Leave Balance": "hr_portal.permissions.leave_balance_query",
	"HR Shift Change Request": "hr_portal.permissions.shift_change_query",
	"HR Payslip": "hr_portal.permissions.payslip_query",
}

has_permission = {
	"HR Employee": "hr_portal.permissions.employee_has_permission",
	"HR Employee Document": "hr_portal.permissions.document_has_permission",
	"HR Attendance": "hr_portal.permissions.attendance_has_permission",
	"HR Regularization": "hr_portal.permissions.regularization_has_permission",
	"HR Leave Request": "hr_portal.permissions.leave_request_has_permission",
	"HR Leave Balance": "hr_portal.permissions.leave_balance_has_permission",
	"HR Shift Change Request": "hr_portal.permissions.shift_change_has_permission",
	"HR Salary Structure": "hr_portal.permissions.payroll_admin_only",
	"HR Payroll Run": "hr_portal.permissions.payroll_admin_only",
	"HR Payslip": "hr_portal.permissions.payslip_has_permission",
	"HR Audit Log": "hr_portal.permissions.audit_log_has_permission",
}

scheduler_events = {
	"cron": {
		"30 6 * * *": ["hr_portal.tasks.daily_attendance_report.send_daily_report"],
	}
}
