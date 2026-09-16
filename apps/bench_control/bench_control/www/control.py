import frappe
from frappe import _

from bench_control.api.auth import check_app_permission

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/control"
		raise frappe.Redirect

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access Bench Control"), frappe.PermissionError)

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()
	context.boot = {
		"csrf_token": csrf_token,
		"site_name": frappe.local.site,
		"user": frappe.session.user,
	}
	return context
