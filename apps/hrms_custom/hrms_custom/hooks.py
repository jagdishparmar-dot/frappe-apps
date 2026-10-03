app_name = "hrms_custom"
app_title = "HRMS"
app_publisher = "HRMS Team"
app_description = "Standalone HRMS on the Frappe Framework: employees, geofenced attendance, onboarding"
app_email = "dev@example.com"
app_license = "mit"
app_logo_url = "/assets/hrms_custom/images/hrms-logo.svg"

add_to_apps_screen = [
	{
		"name": "hrms_custom",
		"logo": "/assets/hrms_custom/images/hrms-logo.svg",
		"title": "HRMS",
		"route": "/desk/hrms",
		"has_permission": "hrms_custom.setup.install.has_app_permission",
	}
]

before_install = "hrms_custom.setup.install.before_install"
after_install = "hrms_custom.setup.install.after_install"
after_migrate = "hrms_custom.setup.install.after_migrate"

extend_bootinfo = ["hrms_custom.boot.extend_bootinfo"]

_EMPLOYEE_SCOPE = "hrms_custom.permissions.employee_permission_query"
_EMPLOYEE_DOC = "hrms_custom.permissions.employee_has_permission"
permission_query_conditions = {
	"Employee": _EMPLOYEE_SCOPE,
	"Leave Application": _EMPLOYEE_SCOPE,
	"Leave Allocation": _EMPLOYEE_SCOPE,
	"Attendance Regularization": _EMPLOYEE_SCOPE,
	"Profile Update Request": _EMPLOYEE_SCOPE,
	"Shift Assignment": _EMPLOYEE_SCOPE,
	"Shift Roster": _EMPLOYEE_SCOPE,
}
has_permission = {
	"Employee": _EMPLOYEE_DOC,
	"Leave Application": _EMPLOYEE_DOC,
	"Leave Allocation": _EMPLOYEE_DOC,
	"Attendance Regularization": _EMPLOYEE_DOC,
	"Profile Update Request": _EMPLOYEE_DOC,
	"Shift Assignment": _EMPLOYEE_DOC,
	"Shift Roster": _EMPLOYEE_DOC,
}
app_include_js = ["/assets/hrms_custom/js/desk_admin_menus.js"]

scheduler_events = {
	"cron": {
		"*/5 * * * *": ["hrms_custom.jobs.shift_reminders.send_shift_reminders"],
	}
}
