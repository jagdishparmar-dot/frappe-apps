app_name = "bench_control"
app_title = "Bench Control"
app_publisher = "Intoship"
app_description = "Manage Frappe sites and apps on a shared bench"
app_email = "dev@intoship.cloud"
app_license = "mit"
app_icon_url = "/assets/bench_control/images/logo.svg"
app_icon_title = "Control"
app_icon_route = "/control"

required_apps = []

add_to_apps_screen = [
	{
		"name": "bench_control",
		"logo": "/assets/bench_control/images/logo.svg",
		"title": "Bench Control",
		"route": "/control",
		"has_permission": "bench_control.api.auth.check_app_permission",
	}
]

website_route_rules = [
	{"from_route": "/control/<path:app_path>", "to_route": "control"},
]

after_install = "bench_control.setup.install.after_install"
after_migrate = "bench_control.setup.install.after_migrate"
