import frappe
from frappe.tests import IntegrationTestCase

from hrms_custom.boot import extend_bootinfo, is_administrator_desk_user, is_restricted_desk_menu
from hrms_custom.tests.utils import get_test_company

HR_ADMIN_USER = "desk.hradmin@example.com"


class TestDeskAdminMenus(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		get_test_company()
		if not frappe.db.exists("User", HR_ADMIN_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_ADMIN_USER, "first_name": "Desk HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Admin")
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_only_administrator_gets_the_desk_admin_flag(self):
		frappe.set_user("Administrator")
		self.assertTrue(is_administrator_desk_user())
		admin_boot = frappe._dict()
		extend_bootinfo(bootinfo=admin_boot)
		self.assertTrue(admin_boot.hrms_administrator_desk)

		frappe.set_user(HR_ADMIN_USER)
		self.assertFalse(is_administrator_desk_user())
		other_boot = frappe._dict()
		extend_bootinfo(bootinfo=other_boot)
		self.assertFalse(other_boot.hrms_administrator_desk)

	def test_edit_sidebar_help_about_and_frappe_support_are_restricted(self):
		for item in (
			{"name": "edit-sidebar", "label": "Edit Sidebar"},
			{"name": "help", "label": "Help"},
			{"label": "About"},
			{"item_label": "About", "action": "frappe.ui.toolbar.show_about()"},
			{"item_label": "Frappe Support", "route": "https://frappe.io/support"},
			{"label": "Frappe Support", "url": "https://support.frappe.io/help"},
		):
			self.assertTrue(is_restricted_desk_menu(item), msg=item)

		for item in (
			{"name": "logout", "label": "Logout"},
			{"label": "Edit Profile"},
			{"label": "Toggle Theme"},
			{"item_label": "Keyboard Shortcuts"},
		):
			self.assertFalse(is_restricted_desk_menu(item), msg=item)

	def test_hooks_load_bootinfo_and_desk_js(self):
		from hrms_custom import hooks

		self.assertIn("hrms_custom.boot.extend_bootinfo", hooks.extend_bootinfo)
		self.assertTrue(any("desk_admin_menus" in path for path in hooks.app_include_js))
