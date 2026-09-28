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
app_include_js = ["/assets/hrms_custom/js/desk_admin_menus.js"]

scheduler_events = {
	"cron": {
		"*/5 * * * *": ["hrms_custom.jobs.shift_reminders.send_shift_reminders"],
	}
}
