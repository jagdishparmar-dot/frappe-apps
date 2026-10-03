import frappe
from frappe.tests import IntegrationTestCase

from hrms_custom.setup.install import has_app_permission
from hrms_custom.tests.utils import get_test_company, make_employee_user

USER_A = "desk.scope.a@example.com"
USER_B = "desk.scope.b@example.com"
HR_USER = "desk.scope.hr@example.com"


class TestEmployeeDeskScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = get_test_company()
		cls.employee_a = make_employee_user(USER_A, cls.company, "Desk Scope A", mobile="9000017101")
		cls.employee_b = make_employee_user(USER_B, cls.company, "Desk Scope B", mobile="9000017102")
		if not frappe.db.exists("User", HR_USER):
			frappe.get_doc(
				{"doctype": "User", "email": HR_USER, "first_name": "Desk Scope HR", "send_welcome_email": 0}
			).insert(ignore_permissions=True).add_roles("HR Executive")
		cls.leave_a = cls._leave(cls.employee_a)
		cls.leave_b = cls._leave(cls.employee_b)
		frappe.db.commit()

	@classmethod
	def _leave(cls, employee):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": employee,
				"leave_type": "Desk Scope Leave",
				"from_date": "2026-04-01",
				"to_date": "2026-04-01",
				"status": "Open",
				"reason": "Scope",
			}
		)
		doc.flags.ignore_validate = True
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		return doc.insert(ignore_permissions=True).name

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in (cls.leave_a, cls.leave_b):
			if frappe.db.exists("Leave Application", name):
				frappe.delete_doc("Leave Application", name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_employee_sees_only_own_leave_and_employee(self):
		other_leave = frappe.get_doc("Leave Application", self.leave_b)
		other_employee = frappe.get_doc("Employee", self.employee_b)
		frappe.set_user(USER_A)
		leaves = frappe.get_list(
			"Leave Application",
			filters={"name": ["in", [self.leave_a, self.leave_b]]},
			pluck="name",
		)
		self.assertEqual(leaves, [self.leave_a])
		self.assertFalse(frappe.has_permission("Leave Application", "read", other_leave))
		self.assertEqual(frappe.get_list("Employee", pluck="name"), [self.employee_a])
		self.assertFalse(frappe.has_permission("Employee", "read", other_employee))

	def test_employee_sees_hrms_launcher(self):
		frappe.set_user(USER_A)
		self.assertTrue(has_app_permission())
		frappe.set_user("Administrator")
		roles = frappe.get_all(
			"Has Role",
			filters={"parenttype": "Desktop Icon", "parent": "HRMS"},
			pluck="role",
		)
		self.assertIn("Employee", roles)

	def test_hr_still_sees_every_employee_record(self):
		frappe.set_user(HR_USER)
		leaves = frappe.get_list(
			"Leave Application",
			filters={"name": ["in", [self.leave_a, self.leave_b]]},
			pluck="name",
		)
		self.assertCountEqual(leaves, [self.leave_a, self.leave_b])
		visible = frappe.get_list(
			"Employee",
			filters={"name": ["in", [self.employee_a, self.employee_b]]},
			pluck="name",
		)
		self.assertCountEqual(visible, [self.employee_a, self.employee_b])
